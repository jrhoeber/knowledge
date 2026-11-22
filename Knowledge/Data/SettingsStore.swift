import Foundation

/// Small preferences kept in `UserDefaults`.
final class SettingsStore {
    private enum Key {
        static let hasCompletedOnboarding = "hasCompletedOnboarding"
        static let enabledTopics = "enabledTopics"
        static let topicBag = "topicScheduler.bag"
        static let topicHistory = "topicScheduler.history"
    }

    private let defaults: UserDefaults

    init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    var hasCompletedOnboarding: Bool {
        get { defaults.bool(forKey: Key.hasCompletedOnboarding) }
        set { defaults.set(newValue, forKey: Key.hasCompletedOnboarding) }
    }

    /// Enabled topics in canonical order. Unavailable topics are never returned.
    var enabledTopics: [Topic] {
        get { topics(forKey: Key.enabledTopics).filter(\.isAvailable) }
        set { setTopics(newValue, forKey: Key.enabledTopics) }
    }

    var schedulerState: TopicScheduler.State {
        get { .init(bag: topics(forKey: Key.topicBag), history: topics(forKey: Key.topicHistory)) }
        set {
            setTopics(newValue.bag, forKey: Key.topicBag)
            setTopics(newValue.history, forKey: Key.topicHistory)
        }
    }

    private func topics(forKey key: String) -> [Topic] {
        (defaults.stringArray(forKey: key) ?? []).compactMap(Topic.init(rawValue:))
    }

    private func setTopics(_ topics: [Topic], forKey key: String) {
        defaults.set(topics.map(\.rawValue), forKey: key)
    }
}
