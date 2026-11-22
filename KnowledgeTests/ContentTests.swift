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

    @Test func vocabularyHasFortyThousandWords() throws {
        #expect(try count("SELECT COUNT(*) FROM vocab_words") == 40_000)
        #expect(try count("SELECT COUNT(DISTINCT word) FROM vocab_words") == 40_000)
        #expect(try count(
            "SELECT COUNT(*) FROM vocab_words w WHERE NOT EXISTS (SELECT 1 FROM vocab_senses s WHERE s.word_id = w.id)"
        ) == 0)
        let provider = try #require(providers[.vocabulary])
        #expect(provider.totalItemCount == 40_000)
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

    @Test func commonWordsAreEasierThanRareOnes() throws {
        let easy = try count("SELECT MAX(frequency_rank) FROM vocab_words WHERE difficulty = 1")
        let hard = try count("SELECT MIN(frequency_rank) FROM vocab_words WHERE difficulty = 5")
        #expect(easy < hard)
    }

    @Test("Vocabulary questions show one correct definition and three from other words", arguments: 1...5)
    func vocabularyQuestionsAreFair(level: Int) throws {
        let provider = try #require(providers[.vocabulary])
        let range = try #require(provider.itemRanges(difficulty: level).first)
        var generator = SeededGenerator(seed: UInt64(level * 1_000))
        for _ in 0..<150 {
            let question = try provider.makeQuestion(itemID: Int.random(in: range, using: &generator), using: &generator)
            guard case .vocabulary(let prompt) = question.content else {
                Issue.record("Expected a vocabulary prompt")
                continue
            }
            let definitions = Set(prompt.meanings.map(\.definition))
            #expect(question.options.count == 4)
            #expect(Set(question.options).count == 4)
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
