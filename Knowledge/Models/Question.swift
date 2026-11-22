import Foundation

/// A single multiple-choice question ready to show on screen.
nonisolated struct Question: Identifiable, Equatable, Sendable {
    let topic: Topic
    /// Stable identifier of the underlying content item within its topic.
    let itemID: Int
    /// 1 (easiest) through 5 (hardest).
    let difficulty: Int
    let content: Content
    let options: [String]
    let correctIndex: Int

    var id: String { "\(topic.rawValue):\(itemID)" }
    var correctAnswer: String { options[correctIndex] }

    enum Content: Equatable, Sendable {
        case math(MathPrompt)
        case vocabulary(VocabularyPrompt)
    }
}

nonisolated struct MathPrompt: Equatable, Sendable {
    enum Operation: String, Sendable, CaseIterable {
        case addition = "+"
        case subtraction = "-"
        case multiplication = "*"
        case division = "/"

        /// Typographically correct operator for display.
        var symbol: String {
            switch self {
            case .addition: "+"
            case .subtraction: "\u{2212}"
            case .multiplication: "\u{00D7}"
            case .division: "\u{00F7}"
            }
        }

        var spokenName: String {
            switch self {
            case .addition: "plus"
            case .subtraction: "minus"
            case .multiplication: "times"
            case .division: "divided by"
            }
        }
    }

    let left: Int
    let operation: Operation
    let right: Int
    let answer: Int

    var expression: String {
        "\(NumberFormatting.string(left)) \(operation.symbol) \(NumberFormatting.string(right))"
    }

    var spokenExpression: String {
        "\(left) \(operation.spokenName) \(right)"
    }
}

nonisolated struct VocabularyPrompt: Equatable, Sendable {
    let word: String
    /// Part of speech of the definition being tested.
    let partOfSpeech: PartOfSpeech
    /// Every common definition of the word (the full answer set), in dictionary order.
    let meanings: [Meaning]
}

nonisolated struct Meaning: Equatable, Sendable, Identifiable {
    let id: Int
    let partOfSpeech: PartOfSpeech
    let definition: String
    let example: String?
}

nonisolated enum PartOfSpeech: String, Sendable, CaseIterable {
    case noun, verb, adjective, adverb, pronoun, preposition, conjunction
    case determiner, interjection, numeral, article, particle
    case other

    init(code: String) {
        switch code {
        case "noun": self = .noun
        case "verb": self = .verb
        case "adj": self = .adjective
        case "adv": self = .adverb
        case "pron": self = .pronoun
        case "prep": self = .preposition
        case "conj": self = .conjunction
        case "det": self = .determiner
        case "intj": self = .interjection
        case "num": self = .numeral
        case "article": self = .article
        case "particle": self = .particle
        default: self = .other
        }
    }

    var label: String { self == .other ? "word" : rawValue }
}

nonisolated enum NumberFormatting {
    static func string(_ value: Int) -> String {
        value.formatted(.number.grouping(.automatic))
    }
}
