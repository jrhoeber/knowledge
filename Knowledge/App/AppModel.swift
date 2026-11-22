import Foundation
import Observation

/// App-wide state: onboarding, enabled topics, and the quiz engine.
@Observable
final class AppModel {
    private(set) var hasCompletedOnboarding: Bool
    private(set) var enabledTopics: [Topic]
    let quiz: QuizEngine

    @ObservationIgnored let progress: ProgressStore
    @ObservationIgnored private let settings: SettingsStore

    init(
        providers: [Topic: any QuestionProvider],
        progress: ProgressStore,
        settings: SettingsStore,
        generator: SeededGenerator = SeededGenerator()
    ) {
        self.progress = progress
        self.settings = settings
        let topics = settings.enabledTopics
        enabledTopics = topics
        hasCompletedOnboarding = settings.hasCompletedOnboarding && !topics.isEmpty
        quiz = QuizEngine(
            providers: providers, progress: progress, settings: settings, topics: topics, generator: generator
        )
    }

    func completeOnboarding(with topics: Set<Topic>) {
        let ordered = Topic.available.filter(topics.contains)
        guard !ordered.isEmpty else { return }
        applyTopics(ordered)
        settings.hasCompletedOnboarding = true
        hasCompletedOnboarding = true
        quiz.start()
    }

    func isEnabled(_ topic: Topic) -> Bool {
        enabledTopics.contains(topic)
    }

    /// The last enabled topic cannot be turned off.
    func canDisable(_ topic: Topic) -> Bool {
        !isEnabled(topic) || enabledTopics.count > 1
    }

    func setEnabled(_ enabled: Bool, for topic: Topic) {
        guard topic.isAvailable else { return }
        var selection = Set(enabledTopics)
        if enabled {
            selection.insert(topic)
        } else {
            guard selection.count > 1 else { return }
            selection.remove(topic)
        }
        applyTopics(Topic.available.filter(selection.contains))
    }

    /// Progress for every available topic, enabled ones first.
    func progressReport() -> [TopicProgress] {
        let ordered = enabledTopics + Topic.available.filter { !enabledTopics.contains($0) }
        return ordered.compactMap { try? progress.topicProgress(for: $0) }
    }

    /// Clears all answers, scores and proficiency in every topic. Topic choices are kept.
    func resetProgress() throws {
        try quiz.resetProgress()
    }

    private func applyTopics(_ topics: [Topic]) {
        settings.enabledTopics = topics
        enabledTopics = topics
        quiz.setTopics(topics)
    }
}
