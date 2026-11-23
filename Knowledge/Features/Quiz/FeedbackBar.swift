import SwiftUI

/// Appears after answering: says whether the answer was right and moves on.
struct FeedbackBar: View {
    let question: Question
    let outcome: QuizEngine.Outcome
    let streak: Int
    let onContinue: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            HStack(alignment: .center, spacing: Spacing.m) {
                Image(systemName: outcome.isCorrect ? "checkmark" : "xmark")
                    .font(.system(size: 17, weight: .heavy))
                    .foregroundStyle(.white)
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(outcome.isCorrect ? Palette.success : Palette.error))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(.title3, design: .rounded, weight: .bold))
                        .foregroundStyle(outcome.isCorrect ? Palette.onSuccessContainer : Palette.onErrorContainer)
                        .accessibilityIdentifier("feedbackTitle")
                    Text(detail)
                        .font(.subheadline)
                        .foregroundStyle(Palette.inkSecondary)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            Button("Continue", action: onContinue)
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityIdentifier("continueButton")
        }
        .padding(.horizontal, Spacing.gutter)
        .padding(.top, Spacing.l)
        .padding(.bottom, Spacing.s)
        .readableWidth()
        .background(
            UnevenRoundedRectangle(topLeadingRadius: Radius.large, topTrailingRadius: Radius.large, style: .continuous)
                .fill(Palette.surface)
                .shadow(color: Palette.ink.opacity(0.08), radius: 12, y: -2)
                .ignoresSafeArea(edges: .bottom)
        )
        .accessibilityElement(children: .contain)
    }

    private var title: String {
        guard outcome.isCorrect else { return "Not quite" }
        return streak >= 3 ? "Correct, \(streak) in a row" : "Correct"
    }

    private var detail: String {
        switch question.content {
        case .math(let prompt):
            return "\(prompt.expression) = \(NumberFormatting.string(prompt.answer))"
        case .vocabulary(let prompt):
            let count = prompt.meanings.count
            return count > 1
                ? "\(prompt.word) has \(count) common meanings, listed below."
                : "The full definition is below."
        case .map(let prompt):
            return "This is \(prompt.target.name), in \(prompt.target.areaName)."
        case .flag(let prompt):
            return "This is the flag of \(prompt.countryName)."
        case .capital(let prompt):
            return "\(prompt.capital) is the capital of \(prompt.placeName)."
        }
    }
}

/// Every common meaning of a vocabulary word, shown after answering.
struct MeaningsCard: View {
    let prompt: VocabularyPrompt
    let topic: Topic

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            HStack(alignment: .firstTextBaseline) {
                Text(prompt.word)
                    .font(.system(.title2, design: .serif, weight: .bold))
                    .foregroundStyle(Palette.ink)
                Spacer()
                Text(prompt.meanings.count == 1 ? "1 meaning" : "\(prompt.meanings.count) meanings")
                    .font(.system(.footnote, design: .rounded, weight: .semibold))
                    .foregroundStyle(topic.colors.onContainer)
                    .padding(.horizontal, Spacing.s)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(topic.colors.container))
            }
            ForEach(Array(prompt.meanings.enumerated()), id: \.element.id) { index, meaning in
                if index > 0 { Divider().overlay(Palette.outline) }
                HStack(alignment: .firstTextBaseline, spacing: Spacing.m) {
                    Text("\(index + 1)")
                        .font(.system(.subheadline, design: .rounded, weight: .bold))
                        .foregroundStyle(topic.colors.accent)
                        .frame(minWidth: 16, alignment: .leading)
                    VStack(alignment: .leading, spacing: Spacing.xs) {
                        Text(meaning.partOfSpeech.label)
                            .font(.system(.footnote, design: .serif).italic())
                            .foregroundStyle(Palette.inkSecondary)
                        Text(meaning.definition)
                            .font(.body)
                            .foregroundStyle(Palette.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if let example = meaning.example {
                            Text("\u{201C}\(example)\u{201D}")
                                .font(.callout)
                                .italic()
                                .foregroundStyle(Palette.inkSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(Spacing.l)
        .cardSurface(radius: Radius.large)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("meaningsCard")
    }
}
