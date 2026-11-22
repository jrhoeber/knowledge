import SwiftUI

struct QuizView: View {
    let engine: QuizEngine
    let openTopics: () -> Void

    var body: some View {
        ZStack {
            Palette.background.ignoresSafeArea()
            if let question = engine.question {
                QuestionView(question: question, outcome: engine.outcome) { index in
                    withAnimation(.easeOut(duration: 0.2)) { engine.select(index) }
                }
                .id(engine.presentationID)
                .transition(.asymmetric(
                    insertion: .move(edge: .trailing).combined(with: .opacity),
                    removal: .move(edge: .leading).combined(with: .opacity)
                ))
            } else if let failure = engine.failureMessage {
                ContentUnavailableView {
                    Label("Questions could not load", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(failure)
                } actions: {
                    Button("Try again") { engine.advance() }
                        .buttonStyle(.borderedProminent)
                }
            } else if engine.topics.isEmpty {
                ContentUnavailableView {
                    Label("No topics selected", systemImage: "square.grid.2x2")
                } description: {
                    Text("Turn on at least one topic to keep practicing.")
                } actions: {
                    Button("Choose topics", action: openTopics)
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ProgressView()
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if let question = engine.question, let outcome = engine.outcome {
                FeedbackBar(question: question, outcome: outcome, streak: engine.streak) {
                    withAnimation(.snappy(duration: 0.32)) { engine.advance() }
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.snappy(duration: 0.25), value: engine.outcome)
        .sensoryFeedback(trigger: engine.outcome) { _, outcome in
            outcome.map { $0.isCorrect ? .success : .error }
        }
    }
}

/// One question: header, prompt and options, plus the full answer set for
/// vocabulary once answered.
private struct QuestionView: View {
    let question: Question
    let outcome: QuizEngine.Outcome?
    let onSelect: (Int) -> Void

    var body: some View {
        ScrollViewReader { proxy in
            content
                .task(id: outcome != nil) {
                    guard outcome != nil, case .vocabulary = question.content else { return }
                    // Bring the full answer set into view above the feedback bar. Wait a
                    // beat so the card and the bar's inset are laid out (and the answer
                    // highlight registers) before scrolling. Anchoring the card's top
                    // clamps to the end for short cards and keeps the first meaning
                    // visible for long ones.
                    try? await Task.sleep(for: .milliseconds(250))
                    guard !Task.isCancelled else { return }
                    withAnimation(.easeInOut(duration: 0.35)) {
                        proxy.scrollTo(Self.meaningsID, anchor: .top)
                    }
                }
        }
    }

    private static let meaningsID = "meanings"

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.l) {
                HStack {
                    TopicChip(topic: question.topic)
                    Spacer()
                    DifficultyMeter(level: question.difficulty, tint: question.topic.colors.accent)
                }
                PromptCard(question: question)
                OptionsView(question: question, outcome: outcome, onSelect: onSelect)
                if outcome != nil, case .vocabulary(let prompt) = question.content {
                    MeaningsCard(prompt: prompt, topic: question.topic)
                        .id(Self.meaningsID)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                }
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.s)
            .padding(.bottom, Spacing.xl)
            .readableWidth()
        }
        .scrollBounceBehavior(.basedOnSize)
    }
}

/// The question itself on a block of the topic's color.
private struct PromptCard: View {
    let question: Question
    @ScaledMetric(relativeTo: .largeTitle) private var expressionSize: CGFloat = 54
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize: CGFloat = 42

    var body: some View {
        VStack(spacing: Spacing.m) {
            switch question.content {
            case .math(let prompt):
                Text("Solve")
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.85))
                Text(prompt.expression)
                    .font(.system(size: expressionSize, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                    .accessibilityLabel(prompt.spokenExpression)
            case .vocabulary(let prompt):
                Text("What does this word mean?")
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.85))
                Text(prompt.word)
                    .font(.system(size: wordSize, weight: .bold, design: .serif))
                    .foregroundStyle(.white)
                    .minimumScaleFactor(0.4)
                    .lineLimit(1)
                Text(prompt.partOfSpeech.label)
                    .font(.system(.callout, design: .serif).italic())
                    .foregroundStyle(.white.opacity(0.9))
            }
        }
        .frame(maxWidth: .infinity, minHeight: 132)
        .padding(.horizontal, Spacing.l)
        .padding(.vertical, Spacing.l)
        .background(
            RoundedRectangle(cornerRadius: Radius.large, style: .continuous)
                .fill(question.topic.colors.accent)
        )
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("questionPrompt")
    }
}

private struct OptionsView: View {
    let question: Question
    let outcome: QuizEngine.Outcome?
    let onSelect: (Int) -> Void

    var body: some View {
        switch question.content {
        case .math:
            LazyVGrid(columns: [GridItem(.flexible(), spacing: Spacing.m), GridItem(.flexible(), spacing: Spacing.m)],
                      spacing: Spacing.m) {
                ForEach(question.options.indices, id: \.self) { index in
                    option(index, layout: .tile)
                }
            }
        case .vocabulary:
            VStack(spacing: Spacing.m) {
                ForEach(question.options.indices, id: \.self) { index in
                    option(index, layout: .row)
                }
            }
        }
    }

    private func option(_ index: Int, layout: OptionButton.Layout) -> some View {
        OptionButton(
            text: question.options[index],
            letter: ["A", "B", "C", "D"][index],
            layout: layout,
            state: state(for: index)
        ) {
            onSelect(index)
        }
        .disabled(outcome != nil)
        .accessibilityIdentifier("option-\(index)")
    }

    private func state(for index: Int) -> OptionButton.State {
        guard let outcome else { return .idle }
        if index == question.correctIndex { return .correct }
        if index == outcome.selectedIndex { return .incorrect }
        return .dimmed
    }
}

struct OptionButton: View {
    enum Layout { case tile, row }
    enum State { case idle, correct, incorrect, dimmed }

    let text: String
    let letter: String
    let layout: Layout
    let state: State
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Group {
                switch layout {
                case .tile:
                    ZStack(alignment: .topTrailing) {
                        Text(text)
                            .font(.system(.title, design: .rounded, weight: .bold))
                            .monospacedDigit()
                            .foregroundStyle(foreground)
                            .minimumScaleFactor(0.6)
                            .lineLimit(1)
                            .frame(maxWidth: .infinity, minHeight: 84)
                        statusIcon
                            .padding(Spacing.s)
                    }
                case .row:
                    HStack(alignment: .firstTextBaseline, spacing: Spacing.m) {
                        Text(letter)
                            .font(.system(.subheadline, design: .rounded, weight: .bold))
                            .foregroundStyle(letterForeground)
                            .frame(width: 28, height: 28)
                            .background(Circle().fill(letterBackground))
                            .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
                        Text(text)
                            .font(.body)
                            .foregroundStyle(foreground)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        statusIcon
                    }
                    .padding(.horizontal, Spacing.l)
                    .padding(.vertical, 14)
                    .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
                }
            }
            .background(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .fill(background)
                    .shadow(color: Palette.ink.opacity(state == .idle ? 0.05 : 0), radius: 2, y: 1)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                    .strokeBorder(border, lineWidth: state == .idle || state == .dimmed ? 1 : 2)
            )
            .opacity(state == .dimmed ? 0.5 : 1)
            .contentShape(RoundedRectangle(cornerRadius: Radius.medium, style: .continuous))
        }
        .buttonStyle(PressableStyle())
        .accessibilityLabel(accessibilityText)
    }

    @ViewBuilder private var statusIcon: some View {
        switch state {
        case .correct:
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Palette.success)
                .transition(.scale.combined(with: .opacity))
        case .incorrect:
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Palette.error)
                .transition(.scale.combined(with: .opacity))
        case .idle, .dimmed:
            EmptyView()
        }
    }

    private var background: Color {
        switch state {
        case .correct: Palette.successContainer
        case .incorrect: Palette.errorContainer
        case .idle, .dimmed: Palette.surface
        }
    }

    private var border: Color {
        switch state {
        case .correct: Palette.success
        case .incorrect: Palette.error
        case .idle, .dimmed: Palette.outline
        }
    }

    private var foreground: Color {
        switch state {
        case .correct: Palette.onSuccessContainer
        case .incorrect: Palette.onErrorContainer
        case .idle, .dimmed: Palette.ink
        }
    }

    private var letterBackground: Color {
        switch state {
        case .correct: Palette.success
        case .incorrect: Palette.error
        case .idle, .dimmed: Palette.surfaceMuted
        }
    }

    private var letterForeground: Color {
        state == .correct || state == .incorrect ? .white : Palette.inkSecondary
    }

    private var accessibilityText: String {
        switch state {
        case .correct: "\(text), correct answer"
        case .incorrect: "\(text), your answer, incorrect"
        case .idle, .dimmed: text
        }
    }
}
