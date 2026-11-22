import SwiftUI

/// Turn topics on and off. Uses a native inset grouped list with toggles.
struct TopicsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        List {
            Section {
                ForEach(Topic.available) { topic in
                    Toggle(isOn: binding(for: topic)) {
                        TopicRow(topic: topic)
                    }
                    .tint(topic.colors.accent)
                    .disabled(!model.canDisable(topic))
                    .accessibilityIdentifier("topicToggle.\(topic.rawValue)")
                    .listRowBackground(Palette.surface)
                }
            } header: {
                Text("Available")
            } footer: {
                Text("Questions rotate evenly between the topics you turn on. At least one topic stays on.")
            }

            Section {
                ForEach(Topic.comingSoon) { topic in
                    HStack(spacing: Spacing.l) {
                        TopicRow(topic: topic, isMuted: true)
                        Spacer(minLength: Spacing.s)
                        Text("Soon")
                            .font(.system(.caption, design: .rounded, weight: .semibold))
                            .foregroundStyle(Palette.inkSecondary)
                            .padding(.horizontal, Spacing.s)
                            .padding(.vertical, 3)
                            .background(Capsule().fill(Palette.surfaceMuted))
                    }
                    .listRowBackground(Palette.surface)
                    .accessibilityElement(children: .combine)
                    .accessibilityHint("Coming soon")
                }
            } header: {
                Text("Coming soon")
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background.ignoresSafeArea())
        .navigationTitle("Topics")
        .navigationBarTitleDisplayMode(.large)
    }

    private func binding(for topic: Topic) -> Binding<Bool> {
        Binding(
            get: { model.isEnabled(topic) },
            set: { model.setEnabled($0, for: topic) }
        )
    }
}

private struct TopicRow: View {
    let topic: Topic
    var isMuted = false

    var body: some View {
        HStack(spacing: Spacing.l) {
            TopicBadge(topic: topic, size: 40, isMuted: isMuted)
            VStack(alignment: .leading, spacing: 2) {
                Text(topic.title)
                    .font(.system(.body, design: .rounded, weight: .semibold))
                    .foregroundStyle(isMuted ? Palette.inkSecondary : Palette.ink)
                Text(topic.summary)
                    .font(.footnote)
                    .foregroundStyle(Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, Spacing.xs)
    }
}
