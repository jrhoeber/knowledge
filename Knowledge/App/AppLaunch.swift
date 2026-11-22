import Foundation
import UIKit

/// Builds the app's dependencies at launch.
///
/// Launch arguments (used by UI tests and for screenshots):
/// - `-resetState`: erase progress and preferences before starting.
/// - `-seed <number>`: make question order deterministic.
/// - `-topics <raw,raw>`: skip onboarding with these topics enabled.
/// - `-disableAnimations`: turn off UIKit animations for faster, steadier UI tests.
enum AppLaunch {
    enum Result {
        case ready(AppModel)
        case failed(String)
    }

    static func start(arguments: [String] = ProcessInfo.processInfo.arguments) -> Result {
        do {
            let defaults = UserDefaults.standard
            let progressURL = try ProgressStore.defaultURL()
            if arguments.contains("-resetState") {
                ProgressStore.deleteStore(at: progressURL)
                if let domain = Bundle.main.bundleIdentifier {
                    defaults.removePersistentDomain(forName: domain)
                }
            }
            if arguments.contains("-disableAnimations") {
                UIView.setAnimationsEnabled(false)
            }

            let settings = SettingsStore(defaults: defaults)
            if let topics = value(after: "-topics", in: arguments) {
                settings.enabledTopics = topics.split(separator: ",").compactMap { Topic(rawValue: String($0)) }
                settings.hasCompletedOnboarding = true
            }
            let generator = value(after: "-seed", in: arguments)
                .flatMap(UInt64.init)
                .map(SeededGenerator.init(seed:)) ?? SeededGenerator()

            let content = try ContentStore.bundled()
            let model = AppModel(
                providers: try content.makeProviders(),
                progress: try ProgressStore(url: progressURL),
                settings: settings,
                generator: generator
            )
            return .ready(model)
        } catch {
            return .failed(String(describing: error))
        }
    }

    private static func value(after flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }
}
