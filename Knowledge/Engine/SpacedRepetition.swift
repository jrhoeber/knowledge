import Foundation

/// When an item should next be reviewed. An item is due once both the answer
/// sequence has reached `dueSequence` and the clock has reached `dueAt`.
nonisolated struct ReviewSchedule: Equatable, Sendable {
    var box: Int
    var dueSequence: Int
    var dueAt: Date
}

/// Leitner-style spaced repetition.
///
/// A missed item drops to box 0 and comes back a handful of questions later in the
/// same session. Each correct review moves it up a box, spacing reviews further
/// apart in both answers and calendar time. Items answered correctly the first time
/// they are seen start in a high box, so they only return occasionally. Missed items
/// therefore come back far more often than known ones.
nonisolated enum SpacedRepetition {
    struct Step: Sendable {
        let answers: Int
        let interval: TimeInterval
    }

    /// Answers until a just-missed item is asked again.
    static let relearnGap = 5...9
    static let firstSeenCorrectBox = 4
    static let maxBox = 6

    private static let minute: TimeInterval = 60
    private static let day: TimeInterval = 86_400

    /// Spacing for boxes 1 through `maxBox`.
    static let steps: [Step] = [
        Step(answers: 15, interval: 10 * minute),
        Step(answers: 30, interval: 1 * day),
        Step(answers: 60, interval: 3 * day),
        Step(answers: 100, interval: 7 * day),
        Step(answers: 150, interval: 21 * day),
        Step(answers: 200, interval: 60 * day),
    ]

    static func schedule(
        previous: ItemState?, isCorrect: Bool, sequence: Int, now: Date, using generator: inout SeededGenerator
    ) -> ReviewSchedule {
        guard isCorrect else {
            let gap = Int.random(in: relearnGap, using: &generator)
            return ReviewSchedule(box: 0, dueSequence: sequence + gap, dueAt: now)
        }
        let box = previous.map { min($0.box + 1, maxBox) } ?? firstSeenCorrectBox
        let step = steps[box - 1]
        return ReviewSchedule(box: box, dueSequence: sequence + step.answers, dueAt: now + step.interval)
    }

    /// Chance that a due review is asked instead of a new question. Recently missed
    /// items (low boxes) almost always win; long-interval reviews are mixed in.
    static func reviewProbability(box: Int) -> Double {
        switch box {
        case 0: 0.9
        case 1: 0.7
        default: 0.35
        }
    }
}
