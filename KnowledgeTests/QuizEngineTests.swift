import Foundation
import Testing
@testable import Knowledge

/// Exercises the question loop end to end against the bundled content and an
/// in-memory progress store.
@Suite(.serialized)
struct QuizEngineTests {
    private static let providers: [Topic: any QuestionProvider] = {
        do {
            return try ContentStore.bundled().makeProviders()
        } catch {
            fatalError("Content failed to load: \(error)")
        }
    }()

    private func makeEngine(topics: [Topic], seed: UInt64) throws -> (QuizEngine, ProgressStore) {
        let progress = try ProgressStore(url: nil)
        let engine = QuizEngine(
            providers: Self.providers, progress: progress, settings: nil, topics: topics,
            generator: SeededGenerator(seed: seed)
        )
        return (engine, progress)
    }

    @Test func alternatesTopicsEvenly() throws {
        let (engine, _) = try makeEngine(topics: [.mentalMath, .vocabulary], seed: 1)
        engine.start()
        var counts: [Topic: Int] = [:]
        var run = 0
        var previous: Topic?
        for index in 0..<40 {
            let question = try #require(engine.question)
            counts[question.topic, default: 0] += 1
            run = question.topic == previous ? run + 1 : 1
            previous = question.topic
            #expect(run <= 2)
            engine.select(index.isMultiple(of: 3) ? (question.correctIndex + 1) % 4 : question.correctIndex)
            engine.advance()
        }
        #expect((18...22).contains(counts[.mentalMath, default: 0]))
        #expect((18...22).contains(counts[.vocabulary, default: 0]))
    }

    @Test("A missed question comes back within the session", arguments: [5, 6, 7, 8])
    func missedQuestionReturns(seed: UInt64) throws {
        let (engine, _) = try makeEngine(topics: [.mentalMath, .vocabulary], seed: seed)
        engine.start()
        let missed = try #require(engine.question)
        engine.select((missed.correctIndex + 1) % 4)
        #expect(engine.outcome?.isCorrect == false)
        engine.advance()

        var returnedAfter: Int?
        for index in 1...25 {
            let question = try #require(engine.question)
            if question.topic == missed.topic, question.itemID == missed.itemID {
                returnedAfter = index
                break
            }
            engine.select(question.correctIndex)
            engine.advance()
        }
        let gap = try #require(returnedAfter, "Missed item did not return within 25 questions")
        #expect(gap >= SpacedRepetition.relearnGap.lowerBound)
    }

    @Test func correctAnswersAreNotRepeatedSoon() throws {
        let (engine, _) = try makeEngine(topics: [.vocabulary], seed: 11)
        engine.start()
        var seen = Set<Int>()
        for _ in 0..<60 {
            let question = try #require(engine.question)
            #expect(!seen.contains(question.itemID))
            seen.insert(question.itemID)
            engine.select(question.correctIndex)
            engine.advance()
        }
    }

    @Test func difficultyIsUniformUntilTenAnswersThenAdapts() throws {
        let (engine, progress) = try makeEngine(topics: [.mentalMath], seed: 3)
        engine.start()
        #expect(Set(try engine.difficultyWeights(in: .mentalMath)).count == 1)
        // Get easy questions right and hard ones wrong.
        for _ in 0..<30 {
            let question = try #require(engine.question)
            engine.select(question.difficulty <= 2 ? question.correctIndex : (question.correctIndex + 1) % 4)
            engine.advance()
        }
        let weights = try engine.difficultyWeights(in: .mentalMath)
        #expect(weights[1] > weights[4])
        #expect(weights[0] > weights[4])
        let report = try progress.topicProgress(for: .mentalMath)
        #expect(report.tally.answered == 30)
        let proficiency = try #require(report.proficiency)
        #expect((2...6).contains(proficiency))
    }

    /// A 10/10 user still sees every level, in about the 10/15/20/25/30% split.
    @Test func topScorersStillSeeEveryLevel() throws {
        let (engine, progress) = try makeEngine(topics: [.mentalMath], seed: 21)
        engine.start()
        var counts = [Int](repeating: 0, count: 5)
        for index in 0..<430 {
            let question = try #require(engine.question)
            if index >= 30 { counts[question.difficulty - 1] += 1 }
            engine.select(question.correctIndex)
            engine.advance()
        }
        #expect(try progress.topicProgress(for: .mentalMath).proficiency == 10)
        for (count, share) in zip(counts, [0.10, 0.15, 0.20, 0.25, 0.30]) {
            #expect(abs(Double(count) / 400 - share) < 0.06, "Served \(counts)")
        }
    }

    /// Missing everything after a perfect start lowers proficiency and brings the easy
    /// levels back. Missed hard questions coming up for review must not crowd them out.
    @Test func strugglingAfterAStrongStartBringsBackEasyLevels() throws {
        let (engine, progress) = try makeEngine(topics: [.mentalMath], seed: 22)
        engine.start()
        for _ in 0..<30 {
            let question = try #require(engine.question)
            engine.select(question.correctIndex)
            engine.advance()
        }
        #expect(try progress.topicProgress(for: .mentalMath).proficiency == 10)

        var levels: [Int] = []
        var expected = [Double](repeating: 0, count: 5)
        for _ in 0..<60 {
            let question = try #require(engine.question)
            levels.append(question.difficulty)
            for (index, weight) in try engine.difficultyWeights(in: .mentalMath).enumerated() {
                expected[index] += weight
            }
            engine.select((question.correctIndex + 1) % 4)
            engine.advance()
        }
        // Every miss is queued for review, yet the levels served still follow the weights.
        for level in 1...5 {
            let served = levels.filter { $0 == level }.count
            #expect(
                abs(Double(served) - expected[level - 1]) <= 8,
                "Level \(level): served \(served), expected \(expected[level - 1]); \(levels)"
            )
        }
        #expect(levels.filter { $0 <= 2 }.count >= 15, "Served \(levels)")
        let proficiency = try #require(try progress.topicProgress(for: .mentalMath).proficiency)
        #expect(proficiency <= 4)
        let weights = try engine.difficultyWeights(in: .mentalMath)
        #expect(weights[0] > weights[4])
    }

    @Test func proficiencyAppearsAfterTenAnswers() throws {
        let (engine, progress) = try makeEngine(topics: [.vocabulary], seed: 9)
        engine.start()
        for answered in 1...10 {
            let question = try #require(engine.question)
            engine.select(question.correctIndex)
            engine.advance()
            let report = try progress.topicProgress(for: .vocabulary)
            #expect(report.tally.answered == answered)
            #expect((report.proficiency != nil) == (answered >= 10))
        }
    }

    @Test func turningOffTheCurrentTopicMovesOn() throws {
        let (engine, _) = try makeEngine(topics: [.mentalMath, .vocabulary], seed: 2)
        engine.start()
        let current = try #require(engine.question)
        let remaining: Topic = current.topic == .mentalMath ? .vocabulary : .mentalMath
        engine.setTopics([remaining])
        #expect(engine.question?.topic == remaining)
        for _ in 0..<6 {
            engine.select(0)
            engine.advance()
            #expect(engine.question?.topic == remaining)
        }
    }

    @Test func gradingRecordsStreaks() throws {
        let (engine, _) = try makeEngine(topics: [.mentalMath], seed: 4)
        engine.start()
        for _ in 0..<3 {
            engine.select(try #require(engine.question).correctIndex)
            engine.advance()
        }
        #expect(engine.streak == 3)
        let question = try #require(engine.question)
        engine.select((question.correctIndex + 1) % 4)
        #expect(engine.streak == 0)
        #expect(engine.sessionAnswered == 4)
        #expect(engine.sessionCorrect == 3)
        // A second tap on the same question is ignored.
        engine.select(question.correctIndex)
        #expect(engine.sessionAnswered == 4)
    }

    @Test func resetProgressClearsHistoryAndProficiency() throws {
        let (engine, progress) = try makeEngine(topics: [.mentalMath, .vocabulary], seed: 9)
        engine.start()
        for index in 0..<30 {
            let question = try #require(engine.question)
            engine.select(index.isMultiple(of: 4) ? (question.correctIndex + 1) % 4 : question.correctIndex)
            engine.advance()
        }
        let before = try progress.topicProgress(for: .mentalMath)
        #expect(before.tally.answered > 0)
        #expect(try progress.seenItemIDs(topic: .vocabulary).isEmpty == false)

        try engine.resetProgress()

        for topic in [Topic.mentalMath, .vocabulary] {
            let report = try progress.topicProgress(for: topic)
            #expect(report.tally == TopicTally())
            #expect(report.proficiency == nil)
            #expect(try progress.seenItemIDs(topic: topic).isEmpty)
            #expect(try engine.difficultyWeights(in: topic) == ProficiencyModel.difficultyWeights(ability: nil))
        }
        #expect(try progress.nextSequence() == 1)
        #expect(engine.streak == 0)
        #expect(engine.sessionAnswered == 0)
        #expect(engine.sessionCorrect == 0)
        #expect(engine.outcome == nil)

        // The loop carries on and records from a clean slate.
        let question = try #require(engine.question)
        engine.select(question.correctIndex)
        #expect(try progress.topicProgress(for: question.topic).tally.answered == 1)
    }
}
