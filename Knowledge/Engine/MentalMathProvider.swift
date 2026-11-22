import Foundation

/// Mental Math questions. Each item is a fixed arithmetic problem with three
/// pre-generated distractors that model common mistakes (off by one, a dropped
/// carry, a neighboring times-table fact).
final class MentalMathProvider: QuestionProvider {
    let topic = Topic.mentalMath
    private let database: SQLiteDatabase
    /// Difficulty → one ID range per operation.
    private let ranges: [Int: [ClosedRange<Int>]]

    init(database: SQLiteDatabase) throws {
        self.database = database
        let rows = try database.query(
            "SELECT difficulty, MIN(id), MAX(id), COUNT(*) FROM math_questions GROUP BY difficulty, operation"
        ) { (difficulty: $0.int(0), first: $0.int(1), last: $0.int(2), count: $0.int(3)) }
        var ranges: [Int: [ClosedRange<Int>]] = [:]
        for row in rows {
            guard row.last - row.first + 1 == row.count else {
                throw QuestionProviderError.nonContiguousRange(table: "math_questions")
            }
            ranges[row.difficulty, default: []].append(row.first...row.last)
        }
        self.ranges = ranges
    }

    func itemRanges(difficulty: Int) -> [ClosedRange<Int>] {
        ranges[difficulty] ?? []
    }

    func makeQuestion(itemID: Int, using generator: inout SeededGenerator) throws -> Question {
        guard let row = try database.queryFirst(
            """
            SELECT operation, lhs, rhs, answer, distractor1, distractor2, distractor3, difficulty
            FROM math_questions WHERE id = ?
            """,
            [.int(itemID)],
            map: { row in
                (operation: row.string(0), lhs: row.int(1), rhs: row.int(2), answer: row.int(3),
                 distractors: [row.int(4), row.int(5), row.int(6)], difficulty: row.int(7))
            }
        ), let operation = MathPrompt.Operation(rawValue: row.operation) else {
            throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
        }

        let values = ([row.answer] + row.distractors).shuffled(using: &generator)
        guard Set(values).count == 4, let correctIndex = values.firstIndex(of: row.answer) else {
            throw QuestionProviderError.notEnoughOptions(topic: topic, itemID: itemID)
        }
        return Question(
            topic: topic,
            itemID: itemID,
            difficulty: row.difficulty,
            content: .math(MathPrompt(left: row.lhs, operation: operation, right: row.rhs, answer: row.answer)),
            options: values.map(NumberFormatting.string),
            correctIndex: correctIndex
        )
    }
}
