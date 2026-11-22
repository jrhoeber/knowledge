import Foundation

/// Vocabulary questions: show a word, pick its definition.
///
/// Each word stores every common definition (the answer set). A question tests one
/// of them, favoring the most common, and fills the other three options with
/// definitions of *other* words that share the tested definition's part of speech
/// and sit at a similar difficulty. Distractors are rejected when they could also be
/// a fair definition of the word: if they come from a listed synonym, mention the
/// word, or share a meaningful word stem with any of its definitions.
final class VocabularyProvider: QuestionProvider {
    let topic = Topic.vocabulary
    private let database: SQLiteDatabase
    private let wordRanges: [Int: ClosedRange<Int>]
    /// Part-of-speech code → difficulty → sense ID range.
    private let senseRanges: [String: [Int: ClosedRange<Int>]]
    private let allSenses: ClosedRange<Int>

    private struct Word {
        let id: Int
        let text: String
        let difficulty: Int
        let related: [String]
    }

    private struct Sense {
        let id: Int
        let partOfSpeech: String
        let gloss: String
        let example: String?
        let isQuizzable: Bool
    }

    private struct Candidate {
        let wordID: Int
        let word: String
        let related: [String]
        let gloss: String
    }

    init(database: SQLiteDatabase) throws {
        self.database = database

        var wordRanges: [Int: ClosedRange<Int>] = [:]
        let wordRows = try database.query(
            "SELECT difficulty, MIN(id), MAX(id), COUNT(*) FROM vocab_words GROUP BY difficulty"
        ) { (difficulty: $0.int(0), first: $0.int(1), last: $0.int(2), count: $0.int(3)) }
        for row in wordRows {
            guard row.last - row.first + 1 == row.count else {
                throw QuestionProviderError.nonContiguousRange(table: "vocab_words")
            }
            wordRanges[row.difficulty] = row.first...row.last
        }
        self.wordRanges = wordRanges

        var senseRanges: [String: [Int: ClosedRange<Int>]] = [:]
        let senseRows = try database.query(
            "SELECT pos, difficulty, MIN(id), MAX(id), COUNT(*) FROM vocab_senses GROUP BY pos, difficulty"
        ) { (pos: $0.string(0), difficulty: $0.int(1), first: $0.int(2), last: $0.int(3), count: $0.int(4)) }
        var lowest = Int.max, highest = Int.min
        for row in senseRows {
            guard row.last - row.first + 1 == row.count else {
                throw QuestionProviderError.nonContiguousRange(table: "vocab_senses")
            }
            senseRanges[row.pos, default: [:]][row.difficulty] = row.first...row.last
            lowest = min(lowest, row.first)
            highest = max(highest, row.last)
        }
        self.senseRanges = senseRanges
        allSenses = lowest <= highest ? lowest...highest : 0...0
    }

    func itemRanges(difficulty: Int) -> [ClosedRange<Int>] {
        wordRanges[difficulty].map { [$0] } ?? []
    }

    /// Word IDs are frequency ranks, so leaning toward the front of a level asks the
    /// words people meet most often first. Rarer words still come up, just less often.
    func randomItem(in range: ClosedRange<Int>, using generator: inout SeededGenerator) -> Int {
        CommonFirstSampler.item(in: range, unit: Double.random(in: 0..<1, using: &generator))
    }

    func makeQuestion(itemID: Int, using generator: inout SeededGenerator) throws -> Question {
        guard let word = try fetchWord(id: itemID) else {
            throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
        }
        let senses = try fetchSenses(wordID: itemID)
        guard !senses.isEmpty else {
            throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
        }

        // Test one definition, strongly favoring the earlier (more common) ones: with
        // several meanings the first is tested a little over half the time.
        let testable = senses.contains(where: \.isQuizzable) ? senses.filter(\.isQuizzable) : senses
        let weights = testable.indices.map { pow(Double($0 + 1), -1.5) }
        let tested = testable[generator.weightedIndex(weights) ?? 0]

        let distractors = try pickDistractors(for: tested, of: word, senses: senses, using: &generator)
        var options = [tested.gloss] + distractors
        options.shuffle(using: &generator)
        guard let correctIndex = options.firstIndex(of: tested.gloss) else {
            throw QuestionProviderError.notEnoughOptions(topic: topic, itemID: itemID)
        }

        let meanings = senses.map {
            Meaning(id: $0.id, partOfSpeech: PartOfSpeech(code: $0.partOfSpeech), definition: $0.gloss, example: $0.example)
        }
        return Question(
            topic: topic,
            itemID: itemID,
            difficulty: word.difficulty,
            content: .vocabulary(VocabularyPrompt(
                word: word.text, partOfSpeech: PartOfSpeech(code: tested.partOfSpeech), meanings: meanings
            )),
            options: options,
            correctIndex: correctIndex
        )
    }

    // MARK: Distractors

    private func pickDistractors(
        for tested: Sense, of word: Word, senses: [Sense], using generator: inout SeededGenerator
    ) throws -> [String] {
        let filter = OverlapFilter(word: word.text, related: word.related, glosses: senses.map(\.gloss))
        var usedGlosses = Set(senses.map { $0.gloss.lowercased() })
        var usedWords: Set<Int> = [word.id]
        var accepted: [Candidate] = []

        for pass in 0..<7 {
            let pool = candidatePool(partOfSpeech: tested.partOfSpeech, difficulty: word.difficulty, pass: pass)
            let ids = (0..<40).map { _ in Int.random(in: pool, using: &generator) }
            for candidate in try fetchCandidates(senseIDs: ids) {
                let key = candidate.gloss.lowercased()
                guard !usedWords.contains(candidate.wordID), !usedGlosses.contains(key),
                      filter.allows(word: candidate.word, related: candidate.related, gloss: candidate.gloss)
                else { continue }
                usedWords.insert(candidate.wordID)
                usedGlosses.insert(key)
                accepted.append(candidate)
            }
            if accepted.count >= 8 { break }
        }
        guard accepted.count >= 3 else {
            throw QuestionProviderError.notEnoughOptions(topic: topic, itemID: word.id)
        }

        // Prefer definitions of similar length so the longest option is not a giveaway.
        let length = tested.gloss.count
        let shortlist = accepted
            .sorted { abs($0.gloss.count - length) < abs($1.gloss.count - length) }
            .prefix(5)
            .shuffled(using: &generator)
        return shortlist.prefix(3).map(\.gloss)
    }

    /// Passes 0–3 draw from the same part of speech within one difficulty level;
    /// passes 4–5 widen to the whole part of speech; the last pass uses everything.
    private func candidatePool(partOfSpeech: String, difficulty: Int, pass: Int) -> ClosedRange<Int> {
        guard let byDifficulty = senseRanges[partOfSpeech], pass < 6 else { return allSenses }
        let window = pass < 4 ? (difficulty - 1)...(difficulty + 1) : 1...5
        let ranges = window.compactMap { byDifficulty[$0] }
        guard let first = ranges.map(\.lowerBound).min(), let last = ranges.map(\.upperBound).max(),
              last - first >= 8
        else { return allSenses }
        // Senses are sorted by part of speech, then difficulty, so this span is contiguous.
        return first...last
    }

    // MARK: Queries

    private func fetchWord(id: Int) throws -> Word? {
        try database.queryFirst(
            "SELECT id, word, difficulty, related FROM vocab_words WHERE id = ?", [.int(id)]
        ) { Word(id: $0.int(0), text: $0.string(1), difficulty: $0.int(2), related: Self.split($0.string(3))) }
    }

    private func fetchSenses(wordID: Int) throws -> [Sense] {
        try database.query(
            "SELECT id, pos, gloss, example, quizzable FROM vocab_senses WHERE word_id = ? ORDER BY sense_order",
            [.int(wordID)]
        ) {
            Sense(id: $0.int(0), partOfSpeech: $0.string(1), gloss: $0.string(2),
                  example: $0.optionalString(3), isQuizzable: $0.bool(4))
        }
    }

    private func fetchCandidates(senseIDs: [Int]) throws -> [Candidate] {
        let placeholders = Array(repeating: "?", count: senseIDs.count).joined(separator: ",")
        return try database.query(
            """
            SELECT s.word_id, w.word, w.related, s.gloss FROM vocab_senses s
            JOIN vocab_words w ON w.id = s.word_id
            WHERE s.id IN (\(placeholders))
            """,
            senseIDs.map(SQLiteValue.int)
        ) { Candidate(wordID: $0.int(0), word: $0.string(1), related: Self.split($0.string(2)), gloss: $0.string(3)) }
    }

    private static func split(_ text: String) -> [String] {
        text.split(separator: " ").map(String.init)
    }
}

/// Maps a uniform draw to a position in a range ordered from most to least common.
///
/// Raising the draw to `bias` skews it toward the front: with a bias of 2, half of the
/// draws land in the first quarter of the range and about 13% in the last quarter.
nonisolated enum CommonFirstSampler {
    static let bias = 2.0

    /// `unit` is a uniform value in `0..<1`.
    static func item(in range: ClosedRange<Int>, unit: Double) -> Int {
        let offset = Int(Double(range.count) * pow(unit, bias))
        return range.lowerBound + min(offset, range.count - 1)
    }
}

/// Decides whether a definition is different enough from a word's own meanings to
/// serve as a wrong answer.
nonisolated struct OverlapFilter {
    private let word: String
    private let related: Set<String>
    private let blockedStems: [String]

    init(word: String, related: [String], glosses: [String]) {
        self.word = word.lowercased()
        self.related = Set(related)
        var stems = Set(GlossTokenizer.contentStems(in: glosses.joined(separator: " ")))
        stems.insert(GlossTokenizer.stem(self.word))
        for term in related {
            stems.insert(GlossTokenizer.stem(term))
        }
        blockedStems = Array(stems)
    }

    func allows(word candidateWord: String, related candidateRelated: [String], gloss: String) -> Bool {
        if related.contains(candidateWord) || candidateRelated.contains(word) { return false }
        var stems = GlossTokenizer.contentStems(in: gloss)
        stems.append(GlossTokenizer.stem(candidateWord))
        for stem in stems where blockedStems.contains(where: { GlossTokenizer.stemsMatch(stem, $0) }) {
            return false
        }
        return true
    }
}

nonisolated enum GlossTokenizer {
    /// Lowercased stems of the meaningful words in `text`.
    static func contentStems(in text: String) -> [String] {
        text.lowercased()
            .split { !$0.isLetter }
            .map(String.init)
            .filter { $0.count >= 3 && !stopWords.contains($0) }
            .map(stem)
    }

    /// A deliberately crude suffix stripper; matching also accepts shared prefixes.
    static func stem(_ word: String) -> String {
        for suffix in suffixes where word.hasSuffix(suffix) && word.count - suffix.count >= 4 {
            return String(word.dropLast(suffix.count))
        }
        return word
    }

    static func stemsMatch(_ a: String, _ b: String) -> Bool {
        if a == b { return true }
        let (short, long) = a.count <= b.count ? (a, b) : (b, a)
        return short.count >= 4 && long.hasPrefix(short)
    }

    private static let suffixes = [
        "ingly", "edly", "ness", "ment", "ings", "ing", "ied", "ies", "ers", "est", "ed", "er", "es", "ly", "s",
    ]

    /// Function words plus words so common in definitions that sharing them says
    /// nothing about meaning.
    static let stopWords: Set<String> = [
        "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had", "her", "was", "one", "our",
        "out", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "two", "way", "who", "did",
        "get", "let", "say", "she", "too", "use", "used", "using", "uses", "that", "this", "with", "from", "they",
        "them", "then", "than", "their", "there", "these", "those", "what", "when", "where", "which", "while",
        "whom", "whose", "will", "would", "could", "should", "been", "being", "have", "having", "into", "onto",
        "upon", "over", "under", "about", "above", "after", "again", "against", "also", "because", "before",
        "below", "between", "both", "down", "during", "each", "even", "ever", "every", "further", "here",
        "just", "more", "most", "much", "must", "only", "other", "others", "same", "some", "such", "very",
        "through", "until", "within", "without", "your", "yours", "something", "someone", "somebody",
        "anything", "anyone", "thing", "things", "person", "people", "one's", "oneself", "itself", "himself",
        "herself", "themselves", "especially", "often", "usually", "generally", "typically", "sometimes",
        "certain", "particular", "particularly", "kind", "kinds", "type", "types", "form", "forms", "part",
        "parts", "act", "action", "state", "quality", "condition", "manner", "process", "relating", "related",
        "pertaining", "characterized", "consisting", "made", "make", "makes", "making", "cause", "causing",
        "become", "becoming", "given", "give", "take", "taken", "like", "able", "done",
        "doing", "does", "group", "number", "amount", "place", "time", "times",
        "another", "instance", "example", "member", "set", "area", "word", "term", "sense",
    ]
}
