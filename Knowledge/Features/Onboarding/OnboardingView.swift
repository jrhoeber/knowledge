import SwiftUI

/// First launch: pick topics, then go straight to questions. No account or
/// permissions are needed.
struct OnboardingView: View {
    @Environment(AppModel.self) private var model
    @State private var selection: Set<Topic> = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xxl) {
                header
                VStack(spacing: Spacing.m) {
                    ForEach(Topic.available) { topic in
                        TopicSelectionCard(topic: topic, isSelected: selection.contains(topic)) {
                            toggle(topic)
                        }
                    }
                }
                comingSoon
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.xxl)
            .padding(.bottom, Spacing.xl)
            .readableWidth()
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Palette.background.ignoresSafeArea())
        .safeAreaInset(edge: .bottom) { startBar }
        .sensoryFeedback(.selection, trigger: selection)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            BrandMark()
            Text("What do you want to practice?")
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
                .foregroundStyle(Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text("Pick one or more topics. Questions adapt to you as you go, and you can change topics any time.")
                .font(.body)
                .foregroundStyle(Palette.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var comingSoon: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            Text("More topics on the way")
                .font(.system(.headline, design: .rounded, weight: .semibold))
                .foregroundStyle(Palette.inkSecondary)
            FlowLayout(spacing: Spacing.s, lineSpacing: Spacing.s) {
                ForEach(Topic.comingSoon) { topic in
                    Label(topic.shortTitle, systemImage: topic.symbolName)
                        .font(.system(.footnote, design: .rounded, weight: .medium))
                        .foregroundStyle(Palette.inkSecondary)
                        .padding(.horizontal, Spacing.m)
                        .padding(.vertical, 7)
                        .background(Capsule().fill(Palette.surfaceMuted))
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var startBar: some View {
        VStack(spacing: Spacing.s) {
            Button("Start practicing") {
                model.completeOnboarding(with: selection)
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(selection.isEmpty)
            .accessibilityIdentifier("startButton")
            Text(selection.isEmpty ? "Choose at least one topic" : selectionSummary)
                .font(.footnote)
                .foregroundStyle(Palette.inkSecondary)
                .contentTransition(.opacity)
        }
        .padding(.horizontal, Spacing.gutter)
        .padding(.top, Spacing.m)
        .padding(.bottom, Spacing.s)
        .readableWidth()
        .background(
            Palette.background
                .overlay(alignment: .top) { Rectangle().fill(Palette.outline).frame(height: 1) }
                .ignoresSafeArea()
        )
    }

    private var selectionSummary: String {
        let names = Topic.available.filter(selection.contains).map(\.title)
        return names.formatted(.list(type: .and))
    }

    private func toggle(_ topic: Topic) {
        if selection.contains(topic) {
            selection.remove(topic)
        } else {
            selection.insert(topic)
        }
    }
}

/// A large, tappable card for choosing a topic.
private struct TopicSelectionCard: View {
    let topic: Topic
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Spacing.l) {
                TopicBadge(topic: topic, size: 52)
                VStack(alignment: .leading, spacing: 3) {
                    Text(topic.title)
                        .font(.system(.headline, design: .rounded, weight: .bold))
                        .foregroundStyle(Palette.ink)
                    Text(topic.summary)
                        .font(.subheadline)
                        .foregroundStyle(Palette.inkSecondary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Spacing.s)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(isSelected ? topic.colors.accent : Palette.outlineStrong)
                    .contentTransition(.symbolEffect(.replace))
            }
            .padding(Spacing.l)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: Radius.large, style: .continuous)
                    .fill(isSelected ? topic.colors.container : Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Radius.large, style: .continuous)
                    .strokeBorder(isSelected ? topic.colors.accent : Palette.outline, lineWidth: isSelected ? 2 : 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: Radius.large, style: .continuous))
        }
        .buttonStyle(PressableStyle(radius: Radius.large))
        .animation(.easeOut(duration: 0.18), value: isSelected)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("topicCard.\(topic.rawValue)")
    }
}

/// The app's wordmark: a row of topic-colored tiles and the name.
struct BrandMark: View {
    var body: some View {
        HStack(spacing: Spacing.s) {
            HStack(spacing: 3) {
                ForEach([Topic.mentalMath, .vocabulary, .geography, .estimation], id: \.self) { topic in
                    RoundedRectangle(cornerRadius: 3, style: .continuous)
                        .fill(topic.colors.accent)
                        .frame(width: 10, height: 10)
                }
            }
            Text("Knowledge")
                .font(.system(.subheadline, design: .rounded, weight: .bold))
                .foregroundStyle(Palette.ink)
                .lineLimit(1)
        }
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Knowledge")
    }
}
