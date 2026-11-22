import Testing
@testable import Knowledge

struct TopicSchedulerTests {
    private let three: [Topic] = [.mentalMath, .vocabulary, .geography]

    @Test("Thirty questions over three topics split about ten each", arguments: 0..<40)
    func balancesTopics(seed: Int) {
        var generator = SeededGenerator(seed: UInt64(seed))
        var scheduler = TopicScheduler(topics: three)
        var counts: [Topic: Int] = [:]
        for _ in 0..<30 {
            counts[scheduler.next(using: &generator)!, default: 0] += 1
        }
        for topic in three {
            #expect((9...11).contains(counts[topic, default: 0]), "\(topic): \(counts[topic, default: 0])")
        }
    }

    @Test("The same topic never appears more than twice in a row", arguments: [2, 3, 5])
    func boundsRuns(topicCount: Int) {
        var generator = SeededGenerator(seed: 99)
        var scheduler = TopicScheduler(topics: Array(Topic.allCases.prefix(topicCount)))
        var previous: Topic?
        var run = 0
        for _ in 0..<2_000 {
            let topic = scheduler.next(using: &generator)!
            run = topic == previous ? run + 1 : 1
            previous = topic
            #expect(run <= TopicScheduler.maxRunLength)
        }
    }

    @Test func singleTopicAlwaysReturnsIt() {
        var generator = SeededGenerator(seed: 1)
        var scheduler = TopicScheduler(topics: [.vocabulary])
        for _ in 0..<10 {
            #expect(scheduler.next(using: &generator) == .vocabulary)
        }
    }

    @Test func noTopicsReturnsNil() {
        var generator = SeededGenerator(seed: 1)
        var scheduler = TopicScheduler(topics: [])
        #expect(scheduler.next(using: &generator) == nil)
    }

    @Test func changingTopicsTakesEffectImmediately() {
        var generator = SeededGenerator(seed: 4)
        var scheduler = TopicScheduler(topics: [.mentalMath, .vocabulary])
        _ = scheduler.next(using: &generator)
        scheduler.setTopics([.vocabulary])
        for _ in 0..<5 {
            #expect(scheduler.next(using: &generator) == .vocabulary)
        }
    }

    @Test func savedBagForOtherTopicsIsDiscarded() {
        let stale = TopicScheduler.State(bag: [.geography, .geography], history: [.geography])
        var generator = SeededGenerator(seed: 2)
        var scheduler = TopicScheduler(topics: [.mentalMath], state: stale)
        #expect(scheduler.next(using: &generator) == .mentalMath)
    }
}
