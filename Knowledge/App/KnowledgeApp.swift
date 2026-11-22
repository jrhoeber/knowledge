import SwiftUI

@main
struct KnowledgeApp: App {
    @State private var launch = AppLaunch.start()

    var body: some Scene {
        WindowGroup {
            switch launch {
            case .ready(let model):
                RootView()
                    .environment(model)
            case .failed(let message):
                StartupFailureView(message: message)
            }
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack {
            if model.hasCompletedOnboarding {
                QuizScreen()
                    .transition(.opacity)
            } else {
                OnboardingView()
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: model.hasCompletedOnboarding)
        .tint(Palette.ink)
    }
}

private struct StartupFailureView: View {
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label("Something went wrong", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        }
        .background(Palette.background)
    }
}
