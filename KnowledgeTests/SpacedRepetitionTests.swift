import Foundation
import Testing
@testable import Knowledge

struct SpacedRepetitionTests {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func state(box: Int) -> ItemState {
        ItemState(topic: .vocabulary, itemID: 1, difficulty: 2, box: box, dueSequence: 0, dueAt: now,
                  seenCount: 1, correctCount: 0, lastSequence: 0)
    }

    @Test func missedItemReturnsWithinTheSession() {
        var generator = SeededGenerator(seed: 3)
        for previous in [nil, state(box: 0), state(box: 5)] {
            let schedule = SpacedRepetition.schedule(
                previous: previous, isCorrect: false, sequence: 100, now: now, using: &generator
            )
            #expect(schedule.box == 0)
            #expect((105...109).contains(schedule.dueSequence))
            #expect(schedule.dueAt == now)
        }
    }

    @Test func firstCorrectAnswerIsSpacedFarOut() {
        var generator = SeededGenerator(seed: 3)
        let schedule = SpacedRepetition.schedule(previous: nil, isCorrect: true, sequence: 10, now: now, using: &generator)
        #expect(schedule.box == SpacedRepetition.firstSeenCorrectBox)
        #expect(schedule.dueAt >= now + 7 * 86_400)
    }

    @Test func correctReviewsClimbAndSpreadOut() {
        var generator = SeededGenerator(seed: 3)
        var previous = state(box: 0)
        var lastGap = 0
        for expectedBox in 1...SpacedRepetition.maxBox {
            let schedule = SpacedRepetition.schedule(
                previous: previous, isCorrect: true, sequence: 0, now: now, using: &generator
            )
            #expect(schedule.box == expectedBox)
            #expect(schedule.dueSequence > lastGap)
            lastGap = schedule.dueSequence
            previous.box = schedule.box
        }
        let capped = SpacedRepetition.schedule(previous: previous, isCorrect: true, sequence: 0, now: now, using: &generator)
        #expect(capped.box == SpacedRepetition.maxBox)
    }

    @Test func missedItemsAreReviewedMoreEagerly() {
        #expect(SpacedRepetition.reviewProbability(box: 0) > SpacedRepetition.reviewProbability(box: 1))
        #expect(SpacedRepetition.reviewProbability(box: 1) > SpacedRepetition.reviewProbability(box: 4))
    }
}
