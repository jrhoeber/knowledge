import Testing
import UIKit
@testable import Knowledge

/// Checks the bundled question bank (`content.sqlite`).
@Suite(.serialized)
struct ContentTests {
    let content: ContentStore
    let providers: [Topic: any QuestionProvider]

    init() throws {
        content = try ContentStore.bundled()
        providers = try content.makeProviders()
    }

    private func count(_ sql: String) throws -> Int {
        try content.database.scalarInt(sql) ?? 0
    }

    // MARK: Mental Math

    @Test func mentalMathHasAtLeastTenThousandUniqueQuestions() throws {
        let total = try count("SELECT COUNT(*) FROM math_questions")
        let unique = try count("SELECT COUNT(*) FROM (SELECT DISTINCT operation, lhs, rhs FROM math_questions)")
        #expect(total >= 10_000)
        #expect(unique == total)
    }

    @Test func mentalMathCoversEveryOperationAtEveryLevel() throws {
        let provider = try #require(providers[.mentalMath])
        for level in 1...5 {
            #expect(provider.itemRanges(difficulty: level).count == MathPrompt.Operation.allCases.count)
        }
    }

    @Test func mentalMathQuestionsAreCorrectMultipleChoice() throws {
        let provider = try #require(providers[.mentalMath])
        var generator = SeededGenerator(seed: 21)
        for level in 1...5 {
            for range in provider.itemRanges(difficulty: level) {
                for _ in 0..<25 {
                    let question = try provider.makeQuestion(itemID: Int.random(in: range, using: &generator), using: &generator)
                    guard case .math(let prompt) = question.content else {
                        Issue.record("Expected a math prompt")
                        continue
                    }
                    let expected = switch prompt.operation {
                    case .addition: prompt.left + prompt.right
                    case .subtraction: prompt.left - prompt.right
                    case .multiplication: prompt.left * prompt.right
                    case .division: prompt.left / prompt.right
                    }
                    #expect(prompt.answer == expected)
                    if prompt.operation == .division { #expect(prompt.left % prompt.right == 0) }
                    #expect(question.options.count == 4)
                    #expect(Set(question.options).count == 4)
                    #expect(question.correctAnswer == NumberFormatting.string(expected))
                    #expect(question.difficulty == level)
                }
            }
        }
    }

    // MARK: Vocabulary

    @Test func vocabularyAsksEveryWordByMeaning() throws {
        let words = try count("SELECT COUNT(*) FROM vocab_words")
        #expect(words >= 30_000)
        #expect(try count("SELECT COUNT(DISTINCT word) FROM vocab_words") == words)
        #expect(try count("SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'vocab_words'") == words)
        // Every word has at least one quiz item, and items are meanings: more items than words.
        #expect(try count("""
            SELECT COUNT(*) FROM vocab_words w WHERE NOT EXISTS
            (SELECT 1 FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id WHERE s.word_id = w.id)
            """) == 0)
        let provider = try #require(providers[.vocabulary])
        #expect(provider.totalItemCount == (try count("SELECT COUNT(*) FROM vocab_items")))
        #expect(provider.totalItemCount > words)
    }

    /// The 3,000 most common words are never asked on their main meaning, which nearly
    /// everyone knows, only on later ones (table: to postpone; bill: a proposed law).
    @Test func commonWordsAreAskedOnlyOnLaterMeanings() throws {
        func items(_ condition: String) throws -> Int {
            try count("""
                SELECT COUNT(*) FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
                JOIN vocab_words w ON w.id = s.word_id WHERE \(condition)
                """)
        }
        #expect(try items("w.frequency_rank <= 3000 AND s.sense_order = 0") == 0)
        #expect(try items("w.frequency_rank <= 3000") > 1_000)
        #expect(try items("w.word = 'table' AND s.gloss LIKE '%postpone%'") == 1)
        #expect(try items("w.word = 'bill' AND s.gloss LIKE '%law%'") == 1)
        #expect(try items("w.word = 'bill' AND s.gloss LIKE '%beak%'") == 0)
    }

    @Test func meaningsThatRestateAMoreCommonWordAreNotAsked() throws {
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('unmusical', 'dreariness', 'shoeless')") == 0)
    }

    /// Wiktionary keeps some definitions under the British spelling (plough, jewellery)
    /// and writes others in it ("an achromatic colour"); the bank uses American spelling.
    @Test func vocabularyUsesAmericanSpelling() throws {
        let british = "'plough', 'jewellery', 'theatre', 'tyre', 'cheque', 'aluminium', 'labour', 'favourite', 'neighbour', 'defence', 'colour', 'centre', 'grey'"
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN (\(british))") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('plow', 'jewelry', 'aluminum', 'neighbor', 'favorite')") == 5)
        for spelling in ["colour", "behaviour", "centre", "travelling", "organisation", "jewellery"] {
            #expect(try count("""
                SELECT COUNT(*) FROM vocab_senses WHERE ' ' || lower(gloss) || ' ' || lower(coalesce(example, '')) || ' '
                GLOB '*[^a-z]\(spelling)[^a-z]*'
                """) == 0, "\(spelling) in a definition or example")
        }
        // Spellings that are also American stay as they are.
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('dialogue', 'axe')") == 2)
    }

    /// Words that used to drop out because of how Wiktionary files them: a definition
    /// too long for a quiz option (journalism), a page-wide slur category (peaceful), a
    /// spaced or accented headword (healthcare, cliche), a synonym-only definition
    /// (mariner), or a derogatory label on an everyday insult (idiot).
    @Test func wellKnownWordsAreNotLostToDictionaryFormatting() throws {
        let words = "'journalism', 'cheetah', 'peaceful', 'authoritarianism', 'healthcare', 'cliche', 'mariner', 'idiot', 'superstition', 'center'"
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN (\(words))") == 10)
        // Insults aimed at a group stay out even though plain insults are in.
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('gringo', 'spinster', 'midget', 'hick')") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_senses WHERE length(gloss) > 220") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_senses WHERE gloss LIKE '%, particularly'") == 0)
    }

    @Test func vocabularyLevelsAreEqualFifths() throws {
        let provider = try #require(providers[.vocabulary])
        let total = Double(provider.totalItemCount)
        for level in 1...5 {
            let share = Double(provider.itemCount(difficulty: level)) / total
            #expect(abs(share - 0.2) < 0.005, "level \(level) holds \(share)")
        }
    }

    @Test func newWordsFavorTheMostCommonInTheirLevel() throws {
        let provider = try #require(providers[.vocabulary])
        let range = try #require(provider.itemRanges(difficulty: 5).first)
        let quarter = range.count / 4
        var generator = SeededGenerator(seed: 11)
        let draws = (0..<4_000).map { _ in provider.randomItem(in: range, using: &generator) }
        #expect(draws.allSatisfy(range.contains))
        let first = Double(draws.filter { $0 < range.lowerBound + quarter }.count) / Double(draws.count)
        let last = Double(draws.filter { $0 > range.upperBound - quarter }.count) / Double(draws.count)
        #expect(abs(first - 0.5) < 0.05, "first quarter share \(first)")
        #expect(last > 0.08, "rare words should still come up; last quarter share \(last)")
        #expect(CommonFirstSampler.item(in: 10...19, unit: 0) == 10)
        #expect(CommonFirstSampler.item(in: 10...19, unit: 0.999_999) == 19)
    }

    /// Difficulty follows how widely a meaning is known, not how common the word is:
    /// "photosynthesis" is rarer than "panacea" in print but far better known.
    @Test func difficultyFollowsHowWidelyAMeaningIsKnown() throws {
        func easiestLevel(_ word: String) throws -> Int {
            try count("""
                SELECT MIN(i.difficulty) FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
                JOIN vocab_words w ON w.id = s.word_id WHERE w.word = '\(word)'
                """)
        }
        func rank(_ word: String) throws -> Int {
            try count("SELECT frequency_rank FROM vocab_words WHERE word = '\(word)'")
        }
        #expect(try rank("photosynthesis") > rank("panacea"))
        #expect(try easiestLevel("photosynthesis") < easiestLevel("panacea"))
        #expect(try easiestLevel("denominator") < easiestLevel("lugubrious"))
        #expect(try easiestLevel("lugubrious") == 5)
    }

    @Test func aWordsMeaningsCanSitAtDifferentLevels() throws {
        #expect(try count("""
            SELECT COUNT(*) FROM (SELECT s.word_id FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
            GROUP BY s.word_id HAVING COUNT(DISTINCT i.difficulty) > 1)
            """) > 1_000)
    }

    @Test("Vocabulary questions show one correct definition and three from other words", arguments: 1...5)
    func vocabularyQuestionsAreFair(level: Int) throws {
        let provider = try #require(providers[.vocabulary])
        let range = try #require(provider.itemRanges(difficulty: level).first)
        var generator = SeededGenerator(seed: UInt64(level * 1_000))
        for _ in 0..<150 {
            let itemID = Int.random(in: range, using: &generator)
            let question = try provider.makeQuestion(itemID: itemID, using: &generator)
            guard case .vocabulary(let prompt) = question.content else {
                Issue.record("Expected a vocabulary prompt")
                continue
            }
            let definitions = Set(prompt.meanings.map(\.definition))
            #expect(question.difficulty == level)
            #expect(question.options.count == 4)
            #expect(Set(question.options).count == 4)
            // The correct option is the item's own meaning.
            let tested = try #require(try content.database.queryFirst(
                "SELECT s.gloss FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id WHERE i.id = ?",
                [.int(itemID)]
            ) { $0.string(0) })
            #expect(question.correctAnswer == tested)
            #expect(definitions.contains(question.correctAnswer))
            let wrong = question.options.enumerated().filter { $0.offset != question.correctIndex }.map(\.element)
            #expect(wrong.allSatisfy { !definitions.contains($0) }, "\(prompt.word): \(wrong)")
            #expect(!prompt.meanings.isEmpty && prompt.meanings.count <= 6)
        }
    }

    @Test func overlapFilterRejectsSynonymsAndSharedRoots() {
        let filter = OverlapFilter(word: "big", related: ["large", "huge"], glosses: ["Of great size, large"])
        #expect(!filter.allows(word: "huge", related: [], gloss: "Extremely sizable"))
        #expect(!filter.allows(word: "vast", related: [], gloss: "Very large in extent"))
        #expect(!filter.allows(word: "tiny", related: ["big"], gloss: "Very small"))
        #expect(filter.allows(word: "quiet", related: [], gloss: "Making little noise"))
    }

    // MARK: Topics

    @Test func everyTopicSymbolExists() {
        for topic in Topic.allCases {
            #expect(UIImage(systemName: topic.symbolName) != nil, "\(topic.symbolName)")
        }
    }

    @Test func onlyMentalMathAndVocabularyAreAvailable() {
        #expect(Topic.available == [.mentalMath, .vocabulary])
        #expect(Topic.comingSoon.count == 16)
        #expect(Set(providers.keys) == Set(Topic.available))
    }
}
