import Foundation

/// Chooses which topic the next question comes from.
///
/// Uses a shuffled "bag": every enabled topic goes into the bag `copiesPerTopic`
/// times, and topics are drawn without replacement until the bag is empty. Over any
/// stretch of questions each topic therefore gets an almost equal share, while the
/// order still feels random. Draws are also constrained so the same topic never
/// appears more than `maxRunLength` times in a row when other topics are enabled.
nonisolated struct TopicScheduler: Sendable {
    struct State: Equatable, Sendable {
        var bag: [Topic] = []
        /// Most recent draws, newest last.
        var history: [Topic] = []
    }

    static let copiesPerTopic = 2
    static let maxRunLength = 2

    private(set) var topics: [Topic]
    private(set) var state: State

    init(topics: [Topic], state: State = State()) {
        self.topics = topics
        self.state = state
        // Discard a saved bag that no longer matches the enabled topics.
        if !state.bag.allSatisfy(topics.contains) {
            self.state.bag = []
        }
        self.state.history = state.history.filter(topics.contains)
    }

    /// Replaces the enabled topics, keeping recent history so runs stay bounded.
    mutating func setTopics(_ newTopics: [Topic]) {
        guard newTopics != topics else { return }
        topics = newTopics
        state.bag = []
        state.history = state.history.filter(newTopics.contains)
    }

    mutating func next(using generator: inout SeededGenerator) -> Topic? {
        guard !topics.isEmpty else { return nil }
        if topics.count == 1 {
            record(topics[0])
            return topics[0]
        }
        if state.bag.isEmpty {
            state.bag = topics.flatMap { Array(repeating: $0, count: Self.copiesPerTopic) }
            state.bag.shuffle(using: &generator)
        }
        // Prefer the first topic in the bag that does not extend a run past the limit.
        let index = state.bag.firstIndex { !wouldExceedRun($0) } ?? 0
        let topic = state.bag.remove(at: index)
        record(topic)
        return topic
    }

    private func wouldExceedRun(_ topic: Topic) -> Bool {
        let recent = state.history.suffix(Self.maxRunLength)
        return recent.count == Self.maxRunLength && recent.allSatisfy { $0 == topic }
    }

    private mutating func record(_ topic: Topic) {
        state.history.append(topic)
        if state.history.count > 8 {
            state.history.removeFirst(state.history.count - 8)
        }
    }
}
