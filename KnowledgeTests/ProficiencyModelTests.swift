import Testing
@testable import Knowledge

struct ProficiencyModelTests {
    /// Newest-first answers cycling through difficulties 1–5.
    private func answers(count: Int, correct: (Int) -> Bool) -> [AnswerRecord] {
        (0..<count).map { index in
            let difficulty = index % 5 + 1
            return AnswerRecord(difficulty: difficulty, isCorrect: correct(difficulty))
        }
    }

    /// Newest-first answers cycling through difficulties 1–5, getting `rates[level - 1]`
    /// of each level right with the misses spread evenly.
    private func answers(count: Int, rates: [Double]) -> [AnswerRecord] {
        let oldestFirst = (0..<count).map { index in
            let difficulty = index % 5 + 1
            let round = Double(index / 5)
            let rate = rates[difficulty - 1]
            return AnswerRecord(difficulty: difficulty, isCorrect: Int((round + 1) * rate) > Int(round * rate))
        }
        return oldestFirst.reversed()
    }

    private func proficiency(_ answers: [AnswerRecord]) -> Int {
        ProficiencyModel.estimate(from: answers).proficiency
    }

    @Test func everythingRightScoresTen() {
        #expect(proficiency(answers(count: 60) { _ in true }) == 10)
    }

    @Test func everythingWrongScoresOne() {
        #expect(proficiency(answers(count: 60) { _ in false }) == 1)
    }

    @Test func guessingScoresOne() {
        #expect(proficiency(answers(count: 120, rates: [0.25, 0.25, 0.25, 0.25, 0.25])) == 1)
    }

    /// A 10 means at least 90% right on level 5, about 97% on level 4 and 99% below.
    @Test func tenMeansNinetyPercentOnTheHardestLevel() {
        let bar = ProficiencyModel.threshold(score: 10)
        let accuracy = (1...5).map { ProficiencyModel.probabilityCorrect(ability: bar, difficulty: $0) }
        #expect(abs(accuracy[4] - 0.9) < 1e-9)
        #expect(accuracy[3] >= 0.95)
        #expect(accuracy[0...2].allSatisfy { $0 >= 0.99 })
    }

    @Test func clearingTheBarScoresTen() {
        #expect(proficiency(answers(count: 120, rates: [1, 1, 1, 0.96, 0.92])) == 10)
    }

    /// Strong, but well short of 90% on the hardest questions.
    @Test func seventyFivePercentOnHardQuestionsIsNotTen() {
        let score = proficiency(answers(count: 120, rates: [1, 0.96, 0.92, 0.83, 0.75]))
        #expect((6...8).contains(score))
    }

    /// A short perfect run is not yet evidence of 90% on the hardest level.
    @Test func aShortPerfectRunIsNotTen() {
        #expect(proficiency(answers(count: 10) { _ in true }) <= 8)
        #expect(proficiency(answers(count: 20) { _ in true }) <= 9)
    }

    @Test func cautiousAbilityIsBelowTheMean() {
        for rates in [[1.0, 1, 1, 1, 1], [1, 0.9, 0.7, 0.5, 0.3], [0, 0, 0, 0, 0]] {
            let estimate = ProficiencyModel.estimate(from: answers(count: 40, rates: rates))
            #expect(estimate.cautiousAbility <= estimate.ability)
        }
    }

    /// The example from the product brief: easy right, hard wrong, medium mixed.
    @Test func mixedResultsFavorMediumQuestions() {
        var records: [AnswerRecord] = []
        for round in 0..<12 {
            records.append(AnswerRecord(difficulty: 1, isCorrect: true))
            records.append(AnswerRecord(difficulty: 2, isCorrect: true))
            records.append(AnswerRecord(difficulty: 3, isCorrect: round.isMultiple(of: 2)))
            records.append(AnswerRecord(difficulty: 4, isCorrect: false))
            records.append(AnswerRecord(difficulty: 5, isCorrect: false))
        }
        let estimate = ProficiencyModel.estimate(from: records.reversed())
        #expect((3...5).contains(estimate.proficiency))
        let weights = ProficiencyModel.difficultyWeights(ability: estimate.ability)
        #expect(weights.max() == weights[2])
        #expect(weights[2] > weights[0])
        #expect(weights[2] > weights[4])
    }

    /// The split from the product owner: a strong user still sees every level, leaning hard.
    @Test func topAbilityLeansGentlyTowardHardQuestions() {
        let top = ProficiencyModel.difficultyWeights(ability: ProficiencyModel.threshold(score: 10))
        for (weight, expected) in zip(top, [0.10, 0.15, 0.20, 0.25, 0.30]) {
            #expect(abs(weight - expected) < 1e-9)
        }
        let bottom = ProficiencyModel.difficultyWeights(ability: 1)
        for (weight, expected) in zip(bottom, [0.30, 0.25, 0.20, 0.15, 0.10]) {
            #expect(abs(weight - expected) < 1e-9)
        }
    }

    @Test func everyLevelKeepsAtLeastTenPercent() {
        for ability in stride(from: -3.0, through: 10.0, by: 0.25) {
            let weights = ProficiencyModel.difficultyWeights(ability: ability)
            #expect(abs(weights.reduce(0, +) - 1) < 1e-9)
            #expect(weights.allSatisfy { $0 >= 0.1 - 1e-9 })
        }
    }

    @Test func higherAbilityMeansHarderOnAverage() {
        var previous = 0.0
        for ability in stride(from: 1.0, through: 5.0, by: 0.25) {
            let weights = ProficiencyModel.difficultyWeights(ability: ability)
            let mean = weights.enumerated().reduce(0) { $0 + Double($1.offset + 1) * $1.element }
            #expect(mean > previous)
            previous = mean
        }
    }

    @Test func unknownAbilityIsUniform() {
        let weights = ProficiencyModel.difficultyWeights(ability: nil)
        #expect(Set(weights).count == 1)
    }

    @Test func proficiencyNeedsTenAnswers() {
        let few = answers(count: 9) { _ in true }
        #expect(ProficiencyModel.proficiency(recent: few, totalAnswered: 9) == nil)
        let enough = answers(count: 10) { _ in true }
        #expect(ProficiencyModel.proficiency(recent: enough, totalAnswered: 10) != nil)
    }

    @Test func recentAnswersOutweighOldOnes() {
        let improving = answers(count: 60) { _ in true } + answers(count: 60) { _ in false }
        let declining = answers(count: 60) { _ in false } + answers(count: 60) { _ in true }
        let up = ProficiencyModel.estimate(from: improving)
        let down = ProficiencyModel.estimate(from: declining)
        #expect(up.ability > down.ability)
        #expect(up.cautiousAbility > down.cautiousAbility)
    }

    @Test func scoreIsBoundedAndMonotonic() {
        var previous = 0
        for ability in stride(from: -3.0, through: 10.0, by: 0.25) {
            let score = ProficiencyModel.score(ability: ability)
            #expect((1...10).contains(score))
            #expect(score >= previous)
            previous = score
        }
    }

    @Test func eachScoreStartsAtItsThreshold() {
        for score in 2...10 {
            let threshold = ProficiencyModel.threshold(score: score)
            #expect(ProficiencyModel.score(ability: threshold + 0.01) == score)
            #expect(ProficiencyModel.score(ability: threshold - 0.01) == score - 1)
        }
    }
}
