import Foundation

/// Every topic the app plans to cover. Only topics with `isAvailable == true` have
/// question content today; the rest are shown as "coming soon" (see TODO.md).
nonisolated enum Topic: String, CaseIterable, Identifiable, Codable, Sendable {
    case mentalMath = "mental_math"
    case geography
    case vocabulary
    case spelling
    case history
    case everydayScience = "everyday_science"
    case spaceEarthWeather = "space_earth_weather"
    case humanBody = "human_body"
    case animalsNature = "animals_nature"
    case money
    case civics
    case estimation
    case idiomsMyths = "idioms_myths"
    case wordRoots = "word_roots"
    case howThingsWork = "how_things_work"
    case economics
    case artsMusic = "arts_music"
    case philosophy

    var id: String { rawValue }

    /// Topics with question content shipped in the app bundle.
    var isAvailable: Bool {
        switch self {
        case .mentalMath, .geography, .vocabulary: true
        default: false
        }
    }

    static var available: [Topic] { allCases.filter(\.isAvailable) }
    static var comingSoon: [Topic] { allCases.filter { !$0.isAvailable } }

    var title: String {
        switch self {
        case .mentalMath: "Mental Math"
        case .geography: "Geography"
        case .vocabulary: "Vocabulary"
        case .spelling: "Spelling"
        case .history: "History"
        case .everydayScience: "Everyday Science"
        case .spaceEarthWeather: "Space, Earth and Weather"
        case .humanBody: "Human Body and Health"
        case .animalsNature: "Animals and Nature"
        case .money: "Money and Personal Finance"
        case .civics: "Civics and Government"
        case .estimation: "Estimation and Everyday Numbers"
        case .idiomsMyths: "Idioms, Myths and Literary References"
        case .wordRoots: "Word Roots"
        case .howThingsWork: "How Things Work"
        case .economics: "Economics in the News"
        case .artsMusic: "Arts and Music"
        case .philosophy: "Philosophy"
        }
    }

    /// Short title for chips and compact layouts.
    var shortTitle: String {
        switch self {
        case .spaceEarthWeather: "Space and Earth"
        case .humanBody: "Human Body"
        case .animalsNature: "Animals and Nature"
        case .money: "Money"
        case .civics: "Civics"
        case .estimation: "Estimation"
        case .idiomsMyths: "Idioms and Myths"
        case .economics: "Economics"
        default: title
        }
    }

    var summary: String {
        switch self {
        case .mentalMath: "Addition, subtraction, multiplication and division"
        case .geography: "Maps, flags and capitals"
        case .vocabulary: "Word meanings, from everyday to rare"
        case .spelling: "Hear a word, then spell it"
        case .history: "Important events and key figures"
        case .everydayScience: "Why the sea is salty and how rainbows form"
        case .spaceEarthWeather: "Planets, seasons, volcanoes and clouds"
        case .humanBody: "Organs, vaccines and nutrition basics"
        case .animalsNature: "Habitats, food chains and how plants grow"
        case .money: "Saving, interest, inflation and budgeting"
        case .civics: "How laws are made and how elections work"
        case .estimation: "Percentages, tips and unit conversions"
        case .idiomsMyths: "Achilles' heel, Pandora's box and more"
        case .wordRoots: "Greek and Latin prefixes and roots"
        case .howThingsWork: "The internet, planes, electricity and phones"
        case .economics: "GDP, tariffs, interest rates and markets"
        case .artsMusic: "Artists, composers and instrument families"
        case .philosophy: "Key thinkers and schools of thought"
        }
    }

    /// SF Symbol name. `TopicTests` verifies every symbol exists.
    var symbolName: String {
        switch self {
        case .mentalMath: "plus.forwardslash.minus"
        case .geography: "globe.americas"
        case .vocabulary: "text.book.closed"
        case .spelling: "speaker.wave.2"
        case .history: "scroll"
        case .everydayScience: "flask"
        case .spaceEarthWeather: "moon.stars"
        case .humanBody: "heart.text.square"
        case .animalsNature: "leaf"
        case .money: "banknote"
        case .civics: "building.columns"
        case .estimation: "percent"
        case .idiomsMyths: "theatermasks"
        case .wordRoots: "character.book.closed"
        case .howThingsWork: "gearshape.2"
        case .economics: "chart.line.uptrend.xyaxis"
        case .artsMusic: "paintpalette"
        case .philosophy: "books.vertical"
        }
    }
}
