import SwiftUI

/// Proficiency (1–10) for each topic, with accuracy by difficulty level.
struct ProfileView: View {
    @Environment(AppModel.self) private var model
    @State private var report: [TopicProgress] = []
    @State private var isConfirmingReset = false
    @State private var resetError: String?

    private var hasProgress: Bool { report.contains { $0.tally.answered > 0 } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.l) {
                SummaryCard(report: report)
                Text("Proficiency")
                    .font(.system(.title3, design: .rounded, weight: .bold))
                    .foregroundStyle(Palette.ink)
                    .padding(.top, Spacing.s)
                ForEach(report) { progress in
                    ProficiencyCard(progress: progress, isEnabled: model.isEnabled(progress.topic))
                }
                Text("Proficiency is based on your recent answers, weighted toward the latest, and on how hard each question was. A 10 means at least 9 in 10 right on the hardest questions. It appears after \(ProficiencyModel.minimumAnswers) answers in a topic.")
                    .font(.footnote)
                    .foregroundStyle(Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                resetSection
                    .padding(.top, Spacing.xl)
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.vertical, Spacing.l)
            .readableWidth()
        }
        .background(Palette.background.ignoresSafeArea())
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.large)
        .onAppear { report = model.progressReport() }
    }

    private var resetSection: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Button("Reset Progress", role: .destructive) {
                isConfirmingReset = true
            }
            .buttonStyle(OutlinedButtonStyle(tint: Palette.error))
            .disabled(!hasProgress)
            .accessibilityIdentifier("resetProgressButton")
            .confirmationDialog(
                "Reset all progress?", isPresented: $isConfirmingReset, titleVisibility: .visible
            ) {
                Button("Reset Progress", role: .destructive, action: resetProgress)
                    .accessibilityIdentifier("confirmResetProgress")
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Every answer, score and proficiency rating in every topic will be permanently deleted. Your topic choices stay the same.")
            }
            if let resetError {
                Text(resetError)
                    .font(.footnote)
                    .foregroundStyle(Palette.error)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func resetProgress() {
        do {
            try model.resetProgress()
            resetError = nil
        } catch {
            resetError = "Your progress could not be reset. \(error)"
        }
        report = model.progressReport()
    }
}

private struct SummaryCard: View {
    let report: [TopicProgress]

    private var answered: Int { report.reduce(0) { $0 + $1.tally.answered } }
    private var correct: Int { report.reduce(0) { $0 + $1.tally.correct } }

    var body: some View {
        HStack(spacing: 0) {
            stat(value: NumberFormatting.string(answered), label: "Answered")
            Divider().frame(height: 44).overlay(Palette.outline)
            stat(value: accuracyText, label: "Accuracy")
            Divider().frame(height: 44).overlay(Palette.outline)
            stat(value: NumberFormatting.string(correct), label: "Correct")
        }
        .padding(.vertical, Spacing.l)
        .cardSurface(radius: Radius.large)
        .accessibilityElement(children: .combine)
    }

    private var accuracyText: String {
        guard answered > 0 else { return "–" }
        return (Double(correct) / Double(answered)).formatted(.percent.precision(.fractionLength(0)))
    }

    private func stat(value: String, label: String) -> some View {
        VStack(spacing: Spacing.xs) {
            Text(value)
                .font(.system(.title2, design: .rounded, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(Palette.ink)
            Text(label)
                .font(.footnote)
                .foregroundStyle(Palette.inkSecondary)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct ProficiencyCard: View {
    let progress: TopicProgress
    let isEnabled: Bool

    private var colors: TopicColors { progress.topic.colors }

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.l) {
            HStack(spacing: Spacing.m) {
                TopicBadge(topic: progress.topic, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(progress.topic.title)
                        .font(.system(.headline, design: .rounded, weight: .bold))
                        .foregroundStyle(Palette.ink)
                    Text(subtitle)
                        .font(.footnote)
                        .foregroundStyle(Palette.inkSecondary)
                }
                Spacer()
                score
            }

            if let proficiency = progress.proficiency {
                SegmentedBar(filled: proficiency, tint: colors.accent)
            } else {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    ProgressView(
                        value: Double(progress.tally.answered),
                        total: Double(ProficiencyModel.minimumAnswers)
                    )
                    .tint(colors.accent)
                    Text(unlockText)
                        .font(.footnote)
                        .foregroundStyle(Palette.inkSecondary)
                }
            }

            DifficultyBreakdown(tally: progress.tally, tint: colors.accent)
        }
        .padding(Spacing.l)
        .cardSurface(radius: Radius.large)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("proficiencyCard.\(progress.topic.rawValue)")
    }

    @ViewBuilder private var score: some View {
        if let proficiency = progress.proficiency {
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text("\(proficiency)")
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .foregroundStyle(colors.accent)
                Text("/10")
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                    .foregroundStyle(Palette.inkSecondary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Proficiency \(proficiency) out of 10")
        } else {
            Text("New")
                .font(.system(.subheadline, design: .rounded, weight: .semibold))
                .foregroundStyle(colors.onContainer)
                .padding(.horizontal, Spacing.m)
                .padding(.vertical, 5)
                .background(Capsule().fill(colors.container))
        }
    }

    private var subtitle: String {
        let answered = progress.tally.answered
        var parts = [answered == 1 ? "1 answer" : "\(NumberFormatting.string(answered)) answers"]
        if let accuracy = progress.tally.accuracy {
            parts.append("\(accuracy.formatted(.percent.precision(.fractionLength(0)))) correct")
        }
        if !isEnabled { parts.append("off") }
        return parts.joined(separator: " · ")
    }

    private var unlockText: String {
        let remaining = progress.answersUntilProficiency
        return remaining == 1
            ? "Answer 1 more question to see your proficiency."
            : "Answer \(remaining) more questions to see your proficiency."
    }
}

/// Accuracy at each of the five difficulty levels.
private struct DifficultyBreakdown: View {
    let tally: TopicTally
    let tint: Color

    var body: some View {
        HStack(alignment: .bottom, spacing: Spacing.s) {
            ForEach(1...5, id: \.self) { level in
                let stats = tally.byDifficulty[level - 1]
                VStack(spacing: Spacing.xs) {
                    Text(stats.accuracy.map { $0.formatted(.percent.precision(.fractionLength(0))) } ?? "–")
                        .font(.system(.caption, design: .rounded, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(stats.answered == 0 ? Palette.inkTertiary : Palette.ink)
                    GeometryReader { proxy in
                        ZStack(alignment: .bottom) {
                            RoundedRectangle(cornerRadius: 4).fill(Palette.surfaceMuted)
                            RoundedRectangle(cornerRadius: 4)
                                .fill(tint)
                                .frame(height: proxy.size.height * (stats.accuracy ?? 0))
                        }
                    }
                    .frame(height: 36)
                    Text("L\(level)")
                        .font(.system(.caption2, design: .rounded, weight: .semibold))
                        .foregroundStyle(Palette.inkSecondary)
                }
                .frame(maxWidth: .infinity)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(label(level: level, stats: stats))
            }
        }
    }

    private func label(level: Int, stats: DifficultyTally) -> String {
        guard let accuracy = stats.accuracy else { return "Level \(level): no answers yet" }
        return "Level \(level): \(accuracy.formatted(.percent.precision(.fractionLength(0)))) of \(stats.answered) correct"
    }
}
