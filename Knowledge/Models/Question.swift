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
        case map(MapPrompt)
        case flag(FlagPrompt)
        case capital(CapitalPrompt)
    }
}

/// Name the country or state highlighted on a map.
nonisolated struct MapPrompt: Equatable, Sendable {
    let atlas: GeoAtlas
    let layer: GeoLayer
    let target: GeoRegion
    /// The region each option names, in option order, so a wrong pick can be shown.
    let optionRegionIDs: [Int]

    var question: String {
        layer == .states ? "Which state is highlighted?" : "Which country is highlighted?"
    }

    static func == (lhs: MapPrompt, rhs: MapPrompt) -> Bool {
        lhs.atlas === rhs.atlas && lhs.layer == rhs.layer && lhs.target == rhs.target
            && lhs.optionRegionIDs == rhs.optionRegionIDs
    }
}

/// A flag image at its true proportions (encoded as WebP).
nonisolated struct FlagImage: Equatable, Sendable {
    let data: Data
    let width: Int
    let height: Int

    var aspectRatio: CGFloat { CGFloat(width) / CGFloat(max(height, 1)) }
}

/// Name the country a flag belongs to.
nonisolated struct FlagPrompt: Equatable, Sendable {
    let countryName: String
    let flag: FlagImage
    /// The flag of the country each option names, in option order.
    let optionFlags: [FlagImage]
    /// Shown after answering, for example when a country has two flags in use.
    let note: String?
}

/// Pick the capital of a country or state.
nonisolated struct CapitalPrompt: Equatable, Sendable {
    let placeName: String
    let isState: Bool
    let capital: String
    /// Shown after answering where capital functions are split (La Paz and Sucre).
    let note: String?
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
