import SwiftUI

/// The home screen: a continuous stream of questions, with a menu leading to
/// Topics and Profile.
struct QuizScreen: View {
    @Environment(AppModel.self) private var model
    @State private var path: [Destination] = []

    enum Destination: Hashable {
        case topics
        case profile
    }

    var body: some View {
        NavigationStack(path: $path) {
            QuizView(engine: model.quiz) {
                path.append(.topics)
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    BrandMark()
                        .padding(.horizontal, Spacing.xs)
                }
                .sharedBackgroundVisibility(.hidden)
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            path.append(.topics)
                        } label: {
                            Label("Topics", systemImage: "square.grid.2x2")
                        }
                        .accessibilityIdentifier("menu.topics")
                        Button {
                            path.append(.profile)
                        } label: {
                            Label("Profile", systemImage: "person.crop.circle")
                        }
                        .accessibilityIdentifier("menu.profile")
                    } label: {
                        Label("Menu", systemImage: "line.3.horizontal")
                            .labelStyle(.iconOnly)
                    }
                    .accessibilityIdentifier("menuButton")
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Destination.self) { destination in
                switch destination {
                case .topics: TopicsView()
                case .profile: ProfileView()
                }
            }
        }
        .onAppear { model.quiz.start() }
    }
}
