import Foundation

/// Supplies questions for one topic from the bundled content database.
///
/// Item IDs at each difficulty are stored contiguously, so a provider describes its
/// pool as ID ranges. The engine picks a range uniformly (so, for example, each math
/// operation is equally likely) and then asks the provider for an item within it.
protocol QuestionProvider: AnyObject {
    var topic: Topic { get }

    /// Non-empty ID ranges holding items at `difficulty` (1–5).
    func itemRanges(difficulty: Int) -> [ClosedRange<Int>]

    /// Draws a new item from `range`. Uniform by default; a provider whose IDs are
    /// ordered by usefulness can lean toward the front.
    func randomItem(in range: ClosedRange<Int>, using generator: inout SeededGenerator) -> Int

    /// Builds a question for an item. Options are shuffled with `generator`.
    func makeQuestion(itemID: Int, using generator: inout SeededGenerator) throws -> Question
}

extension QuestionProvider {
    func randomItem(in range: ClosedRange<Int>, using generator: inout SeededGenerator) -> Int {
        Int.random(in: range, using: &generator)
    }

    func itemCount(difficulty: Int) -> Int {
        itemRanges(difficulty: difficulty).reduce(0) { $0 + $1.count }
    }

    var totalItemCount: Int {
        (1...5).reduce(0) { $0 + itemCount(difficulty: $1) }
    }
}

nonisolated enum QuestionProviderError: Error, CustomStringConvertible {
    case missingItem(topic: Topic, itemID: Int)
    case notEnoughOptions(topic: Topic, itemID: Int)
    case nonContiguousRange(table: String)

    var description: String {
        switch self {
        case let .missingItem(topic, itemID): "No \(topic.title) item with ID \(itemID)."
        case let .notEnoughOptions(topic, itemID): "Could not build four options for \(topic.title) item \(itemID)."
        case let .nonContiguousRange(table): "Item IDs in \(table) are not contiguous by difficulty."
        }
    }
}
