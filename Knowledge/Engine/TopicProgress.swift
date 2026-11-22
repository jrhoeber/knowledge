import Foundation

/// What the Profile screen shows for one topic.
nonisolated struct TopicProgress: Identifiable, Equatable, Sendable {
    let topic: Topic
    let tally: TopicTally
    /// 1–10, or `nil` until `ProficiencyModel.minimumAnswers` questions are answered.
    let proficiency: Int?

    var id: Topic { topic }

    var answersUntilProficiency: Int {
        max(ProficiencyModel.minimumAnswers - tally.answered, 0)
    }
}

extension ProgressStore {
    func topicProgress(for topic: Topic) throws -> TopicProgress {
        let tally = try tally(topic: topic)
        let recent = try recentAnswers(topic: topic, limit: ProficiencyModel.recentWindow)
        return TopicProgress(
            topic: topic,
            tally: tally,
            proficiency: ProficiencyModel.proficiency(recent: recent, totalAnswered: tally.answered)
        )
    }
}
