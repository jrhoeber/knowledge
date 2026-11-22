import Foundation
import Observation

/// Runs the question loop: picks what to ask next, grades answers, and records
/// progress.
///
/// Choosing the next question happens in three steps:
/// 1. `TopicScheduler` picks a topic so enabled topics get an even share.
/// 2. If an item in that topic is due for review (spaced repetition), it may be
///    asked again; recently missed items almost always are.
/// 3. Otherwise a new, unseen item is chosen at a difficulty drawn from the
///    topic's `ProficiencyModel` weights (uniform until 10 answers exist).
@Observable
final class QuizEngine {
    struct Outcome: Equatable {
        let selectedIndex: Int
        let isCorrect: Bool
    }

    private(set) var question: Question?
    /// Changes every time a question is shown, even when the same item repeats.
    private(set) var presentationID = 0
    private(set) var outcome: Outcome?
    private(set) var failureMessage: String?
    private(set) var topics: [Topic]
    private(set) var streak = 0
    private(set) var sessionAnswered = 0
    private(set) var sessionCorrect = 0

    @ObservationIgnored private let providers: [Topic: any QuestionProvider]
    @ObservationIgnored private let progress: ProgressStore
    @ObservationIgnored private let settings: SettingsStore?
    @ObservationIgnored private let now: () -> Date
    @ObservationIgnored private var scheduler: TopicScheduler
    @ObservationIgnored private var generator: SeededGenerator
    @ObservationIgnored private var seenItems: [Topic: Set<Int>] = [:]
    @ObservationIgnored private var lastItemID: [Topic: Int] = [:]

    init(
        providers: [Topic: any QuestionProvider],
        progress: ProgressStore,
        settings: SettingsStore?,
        topics: [Topic],
        generator: SeededGenerator,
        now: @escaping () -> Date = Date.init
    ) {
        let usable = topics.filter { providers[$0] != nil }
        self.providers = providers
        self.progress = progress
        self.settings = settings
        self.topics = usable
        self.generator = generator
        self.now = now
        scheduler = TopicScheduler(topics: usable, state: settings?.schedulerState ?? .init())
    }

    // MARK: Public API

    /// Loads the first question if none is showing.
    func start() {
        if question == nil { advance() }
    }

    func setTopics(_ newTopics: [Topic]) {
        let usable = newTopics.filter { providers[$0] != nil }
        guard usable != topics else { return }
        topics = usable
        scheduler.setTopics(usable)
        settings?.schedulerState = scheduler.state
        if usable.isEmpty {
            question = nil
            outcome = nil
        } else if let question, !usable.contains(question.topic), outcome == nil {
            advance()
        }
    }

    /// Grades the option at `index` and records the answer.
    func select(_ index: Int) {
        guard let question, outcome == nil, question.options.indices.contains(index) else { return }
        let isCorrect = index == question.correctIndex
        outcome = Outcome(selectedIndex: index, isCorrect: isCorrect)
        sessionAnswered += 1
        if isCorrect {
            sessionCorrect += 1
            streak += 1
        } else {
            streak = 0
        }
        do {
            try record(question, isCorrect: isCorrect)
        } catch {
            failureMessage = "Your answer could not be saved. \(error)"
        }
    }

    /// Erases every recorded answer and review schedule, so proficiency starts over,
    /// and replaces the current question (it was chosen from the old history).
    func resetProgress() throws {
        try progress.deleteAll()
        seenItems = [:]
        lastItemID = [:]
        streak = 0
        sessionAnswered = 0
        sessionCorrect = 0
        question = nil
        advance()
    }

    /// Moves on to the next question.
    func advance() {
        outcome = nil
        var lastError: Error?
        // An individual item can fail to build (for example, too few distinct
        // distractors); try a few others before giving up.
        for _ in 0..<5 {
            do {
                question = try makeNextQuestion()
                presentationID += 1
                failureMessage = nil
                return
            } catch {
                lastError = error
            }
        }
        question = nil
        failureMessage = lastError.map { "Could not load a question. \($0)" }
    }

    // MARK: Selection

    func makeNextQuestion() throws -> Question? {
        guard let topic = scheduler.next(using: &generator), let provider = providers[topic] else { return nil }
        settings?.schedulerState = scheduler.state
        let itemID = try chooseItem(in: topic, provider: provider)
        lastItemID[topic] = itemID
        return try provider.makeQuestion(itemID: itemID, using: &generator)
    }

    private func chooseItem(in topic: Topic, provider: any QuestionProvider) throws -> Int {
        // Difficulty comes first, so the levels served always follow the weights. A
        // due review at that level takes priority over a new question; reviews at
        // other levels wait until their level comes up. (Choosing reviews first let
        // a run of missed hard questions crowd out the easy levels.)
        let difficulty = try plannedDifficulty(in: topic, provider: provider)
        let sequence = try progress.nextSequence()
        let due = try progress.dueItems(
            topic: topic, difficulty: difficulty, sequence: sequence, now: now(), limit: 3
        )
        if let review = due.first(where: { $0.itemID != lastItemID[topic] }),
           Double.random(in: 0..<1, using: &generator) < SpacedRepetition.reviewProbability(box: review.box) {
            return review.itemID
        }

        if let fresh = try unseenItem(in: topic, difficulty: difficulty, provider: provider) {
            return fresh
        }
        // Every item at this level has been seen: reuse the one seen longest ago.
        if let reused = try progress.leastRecentlySeenItem(
            topic: topic, difficulty: difficulty, excluding: lastItemID[topic]
        ) {
            return reused
        }
        for level in (1...5).shuffled(using: &generator) {
            if let fresh = try unseenItem(in: topic, difficulty: level, provider: provider) { return fresh }
        }
        let ranges = (1...5).flatMap { provider.itemRanges(difficulty: $0) }
        guard let range = ranges.randomElement(using: &generator) else {
            throw QuestionProviderError.missingItem(topic: topic, itemID: -1)
        }
        return Int.random(in: range, using: &generator)
    }

    /// Difficulty for the next question in `topic`.
    func plannedDifficulty(in topic: Topic, provider: any QuestionProvider) throws -> Int {
        let weights = try difficultyWeights(in: topic).enumerated().map { level, weight in
            provider.itemCount(difficulty: level + 1) > 0 ? weight : 0
        }
        return (generator.weightedIndex(weights) ?? 0) + 1
    }

    /// Share of questions at each difficulty, from the best estimate of ability (not
    /// the cautious one behind the proficiency shown on Profile).
    func difficultyWeights(in topic: Topic) throws -> [Double] {
        let total = try progress.answerCount(topic: topic)
        let recent = try progress.recentAnswers(topic: topic, limit: ProficiencyModel.recentWindow)
        let estimate = ProficiencyModel.estimate(recent: recent, totalAnswered: total)
        return ProficiencyModel.difficultyWeights(ability: estimate?.ability)
    }

    private func unseenItem(in topic: Topic, difficulty: Int, provider: any QuestionProvider) throws -> Int? {
        let seen = try seenItemIDs(topic)
        // Shuffling the ranges first gives each range (for math, each operation) an equal chance.
        // The provider chooses where in a range to draw (vocabulary leans toward common words).
        for range in provider.itemRanges(difficulty: difficulty).shuffled(using: &generator) {
            for _ in 0..<24 {
                let candidate = provider.randomItem(in: range, using: &generator)
                if !seen.contains(candidate) { return candidate }
            }
            // The scan walks toward rarer items, so with a front-leaning provider it
            // finds the next most common unseen one.
            let start = provider.randomItem(in: range, using: &generator)
            if let candidate = (start...range.upperBound).first(where: { !seen.contains($0) })
                ?? (range.lowerBound..<start).first(where: { !seen.contains($0) }) {
                return candidate
            }
        }
        return nil
    }

    private func seenItemIDs(_ topic: Topic) throws -> Set<Int> {
        if let cached = seenItems[topic] { return cached }
        let loaded = try progress.seenItemIDs(topic: topic)
        seenItems[topic] = loaded
        return loaded
    }

    // MARK: Recording

    private func record(_ question: Question, isCorrect: Bool) throws {
        let sequence = try progress.nextSequence()
        let timestamp = now()
        let previous = try progress.state(topic: question.topic, itemID: question.itemID)
        let schedule = SpacedRepetition.schedule(
            previous: previous, isCorrect: isCorrect, sequence: sequence, now: timestamp, using: &generator
        )
        try progress.record(
            topic: question.topic, itemID: question.itemID, difficulty: question.difficulty,
            isCorrect: isCorrect, sequence: sequence, now: timestamp, schedule: schedule
        )
        var seen = try seenItemIDs(question.topic)
        seen.insert(question.itemID)
        seenItems[question.topic] = seen
    }
}
