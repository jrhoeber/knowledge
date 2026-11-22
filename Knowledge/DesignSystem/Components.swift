import SwiftUI

// MARK: Layout

nonisolated enum Spacing {
    static let xs: CGFloat = 4
    static let s: CGFloat = 8
    static let m: CGFloat = 12
    static let l: CGFloat = 16
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
    /// Horizontal screen margin.
    static let gutter: CGFloat = 20
    /// Content stops growing past this width on iPad.
    static let readableWidth: CGFloat = 620
}

nonisolated enum Radius {
    static let small: CGFloat = 10
    static let medium: CGFloat = 16
    static let large: CGFloat = 24
}

extension View {
    /// White card with a hairline outline and low elevation.
    func cardSurface(radius: CGFloat = Radius.medium) -> some View {
        background(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(Palette.surface)
                .shadow(color: Palette.ink.opacity(0.05), radius: 2, y: 1)
        )
        .overlay(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(Palette.outline, lineWidth: 1)
        )
    }

    /// Centers content and caps its width for large screens.
    func readableWidth() -> some View {
        frame(maxWidth: Spacing.readableWidth).frame(maxWidth: .infinity)
    }
}

// MARK: Buttons

/// Full-width filled button used for the main action on a screen.
struct PrimaryButtonStyle: ButtonStyle {
    var fill: Color = Palette.ink
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.headline, design: .rounded, weight: .semibold))
            .foregroundStyle(isEnabled ? Color.white : Palette.inkTertiary)
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .fill(isEnabled ? fill : Palette.surfaceMuted)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.12 : 0))
            )
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// Full-width outlined button on a white surface, for secondary or destructive actions.
struct OutlinedButtonStyle: ButtonStyle {
    var tint: Color = Palette.ink
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.headline, design: .rounded, weight: .semibold))
            .foregroundStyle(isEnabled ? tint : Palette.inkTertiary)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .fill(Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .fill(tint.opacity(configuration.isPressed ? 0.08 : 0))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .strokeBorder(Palette.outlineStrong, lineWidth: 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: Radius.medium, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// Adds a pressed-state overlay (Material "state layer") to custom tappable surfaces.
struct PressableStyle: ButtonStyle {
    var radius: CGFloat = Radius.medium

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(Palette.ink.opacity(configuration.isPressed ? 0.06 : 0))
                    .allowsHitTesting(false)
            )
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

// MARK: Topic visuals

/// Rounded square in the topic color with the topic's symbol.
struct TopicBadge: View {
    let topic: Topic
    var size: CGFloat = 44
    var isMuted = false

    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.28, style: .continuous)
            .fill(isMuted ? Palette.surfaceMuted : topic.colors.accent)
            .frame(width: size, height: size)
            .overlay(
                Image(systemName: topic.symbolName)
                    .font(.system(size: size * 0.44, weight: .semibold))
                    .foregroundStyle(isMuted ? Palette.inkTertiary : Color.white)
            )
            .accessibilityHidden(true)
    }
}

/// Small tinted capsule naming a topic.
struct TopicChip: View {
    let topic: Topic

    var body: some View {
        Label(topic.shortTitle, systemImage: topic.symbolName)
            .font(.system(.subheadline, design: .rounded, weight: .semibold))
            .foregroundStyle(topic.colors.onContainer)
            .padding(.horizontal, Spacing.m)
            .padding(.vertical, 6)
            .background(Capsule().fill(topic.colors.container))
    }
}

/// Five bars showing a question's difficulty level.
struct DifficultyMeter: View {
    let level: Int
    var tint: Color = Palette.ink

    var body: some View {
        HStack(spacing: Spacing.s) {
            Text("Level \(level)")
                .font(.system(.subheadline, design: .rounded, weight: .semibold))
                .foregroundStyle(Palette.inkSecondary)
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(1...5, id: \.self) { step in
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(step <= level ? tint : Palette.outlineStrong)
                        .frame(width: 5, height: 6 + CGFloat(step) * 2.4)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Difficulty level \(level) of 5")
    }
}

/// Horizontal bar of `total` segments with `filled` of them colored.
struct SegmentedBar: View {
    let filled: Int
    var total = 10
    var tint: Color
    var height: CGFloat = 10

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<total, id: \.self) { index in
                Capsule()
                    .fill(index < filled ? tint : Palette.surfaceMuted)
                    .frame(height: height)
            }
        }
        .accessibilityHidden(true)
    }
}

/// Wraps children onto new lines like text.
struct FlowLayout: Layout {
    var spacing: CGFloat = Spacing.s
    var lineSpacing: CGFloat = Spacing.s

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.last.map { $0.y + $0.height } ?? 0
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = arrange(width: bounds.width, subviews: subviews)
        for row in rows {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: bounds.minY + row.y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
        }
    }

    private struct Row {
        var indices: [Int] = []
        var y: CGFloat = 0
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = []
        var current = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let proposedWidth = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if proposedWidth > width, !current.indices.isEmpty {
                rows.append(current)
                current = Row(y: current.y + current.height + lineSpacing)
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }
}
