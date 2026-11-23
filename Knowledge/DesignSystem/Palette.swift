import SwiftUI

/// Color roles, loosely following Material's scheme (surface, on-surface,
/// container, on-container). The app uses a light appearance only: a bright warm
/// background with saturated topic colors as accents.
enum Palette {
    static let background = Color(hex: 0xFFF8F0)
    static let surface = Color.white
    static let surfaceMuted = Color(hex: 0xF6EEE4)
    static let outline = Color(hex: 0xEADFD2)
    static let outlineStrong = Color(hex: 0xD9CCBC)

    static let ink = Color(hex: 0x1C1A24)
    static let inkSecondary = Color(hex: 0x625C6E)
    static let inkTertiary = Color(hex: 0x9A93A3)

    static let success = Color(hex: 0x14A155)
    static let successContainer = Color(hex: 0xE1F6E9)
    static let onSuccessContainer = Color(hex: 0x0B6533)

    static let error = Color(hex: 0xE23B2E)
    static let errorContainer = Color(hex: 0xFDE6E3)
    static let onErrorContainer = Color(hex: 0x9C1C13)

    /// Maps: pale water, warm neutral land and soft borders, so the highlighted place
    /// (in the Geography color) is the only saturated fill.
    static let mapWater = Color(hex: 0xD8EAF1)
    static let mapLand = Color(hex: 0xF6F0E6)
    static let mapBorder = Color(hex: 0xB4A694)
}

struct TopicColors {
    /// Strong accent, used for fills behind white text and for progress.
    let accent: Color
    /// Light tint for chips and selected states.
    let container: Color
    /// Text and icons placed on `container`.
    let onContainer: Color
}

extension Topic {
    var colors: TopicColors {
        switch self {
        case .mentalMath: TopicColors(accent: Color(hex: 0xF2541B), container: Color(hex: 0xFFE9DF), onContainer: Color(hex: 0x962D05))
        case .vocabulary: TopicColors(accent: Color(hex: 0x2D5BE3), container: Color(hex: 0xE4EBFD), onContainer: Color(hex: 0x173A9E))
        case .geography: TopicColors(accent: Color(hex: 0x0E9F86), container: Color(hex: 0xDDF4EF), onContainer: Color(hex: 0x07614F))
        case .spelling: TopicColors(accent: Color(hex: 0xDB3A82), container: Color(hex: 0xFCE4EF), onContainer: Color(hex: 0x8C1A4D))
        case .history: TopicColors(accent: Color(hex: 0xB86A1E), container: Color(hex: 0xF8EAD9), onContainer: Color(hex: 0x6E3C0B))
        case .everydayScience: TopicColors(accent: Color(hex: 0x0A9AD6), container: Color(hex: 0xDDF2FB), onContainer: Color(hex: 0x05607F))
        case .spaceEarthWeather: TopicColors(accent: Color(hex: 0x4B3FC4), container: Color(hex: 0xE8E6FA), onContainer: Color(hex: 0x2A2183))
        case .humanBody: TopicColors(accent: Color(hex: 0xE5485F), container: Color(hex: 0xFDE5E9), onContainer: Color(hex: 0x951C30))
        case .animalsNature: TopicColors(accent: Color(hex: 0x3D9A40), container: Color(hex: 0xE2F3E2), onContainer: Color(hex: 0x1F5E22))
        case .money: TopicColors(accent: Color(hex: 0x16865A), container: Color(hex: 0xDDF2E8), onContainer: Color(hex: 0x0B5235))
        case .civics: TopicColors(accent: Color(hex: 0x2F62AE), container: Color(hex: 0xE2EAF6), onContainer: Color(hex: 0x173B70))
        case .estimation: TopicColors(accent: Color(hex: 0xE3A100), container: Color(hex: 0xFFF2D1), onContainer: Color(hex: 0x7A5600))
        case .idiomsMyths: TopicColors(accent: Color(hex: 0x8E46B3), container: Color(hex: 0xF1E5F8), onContainer: Color(hex: 0x56236F))
        case .wordRoots: TopicColors(accent: Color(hex: 0xC2412F), container: Color(hex: 0xF9E3DF), onContainer: Color(hex: 0x7A2215))
        case .howThingsWork: TopicColors(accent: Color(hex: 0x56677C), container: Color(hex: 0xE6EAEF), onContainer: Color(hex: 0x2F3B4A))
        case .economics: TopicColors(accent: Color(hex: 0x0D7F8F), container: Color(hex: 0xDCEFF1), onContainer: Color(hex: 0x064C56))
        case .artsMusic: TopicColors(accent: Color(hex: 0xD2445C), container: Color(hex: 0xFAE3E7), onContainer: Color(hex: 0x841F31))
        case .philosophy: TopicColors(accent: Color(hex: 0x6B4FA6), container: Color(hex: 0xEDE7F6), onContainer: Color(hex: 0x3E2A68))
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
