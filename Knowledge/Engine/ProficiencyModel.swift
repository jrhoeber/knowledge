import Foundation

/// Estimates how proficient the user is in a topic and turns that into question
/// difficulty weights.
///
/// The model is a one-parameter logistic (Rasch) model on the 1–5 difficulty scale:
/// the chance of answering a level-`d` question correctly is
/// `1 / (1 + exp(-slope * (ability - d)))`. An ability of 3 means the user gets
/// level-3 questions right about half the time.
///
/// Ability is a Bayesian estimate over the most recent answers, with newer answers
/// weighted more heavily and a weak prior centered on medium difficulty. Two
/// numbers come out of it:
/// - the posterior mean, the best guess, which picks question difficulty;
/// - a cautious estimate (the 40th percentile), which the 1–10 proficiency is based
///   on, so a high score needs evidence and a short lucky run cannot earn one.
nonisolated enum ProficiencyModel {
    struct Estimate: Equatable, Sendable {
        /// Posterior mean.
        let ability: Double
        /// Posterior 40th percentile: the user is more likely than not at least this good.
        let cautiousAbility: Double

        var proficiency: Int { ProficiencyModel.score(ability: cautiousAbility) }
    }

    /// Answers required in a topic before proficiency is shown or used.
    static let minimumAnswers = 10
    /// How many recent answers feed the estimate.
    static let recentWindow = 120
    /// An answer this many answers old counts half as much as the newest one.
    static let halfLife = 60.0
    static let slope = 1.4
    static let priorMean = 3.0
    static let priorStandardDeviation = 2.0
    /// Posterior percentile the shown proficiency is based on.
    static let cautiousQuantile = 0.4

    /// A 10 means level-5 questions are answered right at least this often. Under
    /// the model that also means about 97% on level 4 and 99% or more below.
    static let topAccuracy = 0.9
    /// Ability needed for a 10.
    static let topAbility = 5 + log(topAccuracy / (1 - topAccuracy)) / slope
    /// Ability per proficiency point: each point down is the same accuracy at a
    /// level 0.6 easier.
    static let abilityPerPoint = 0.6

    /// Abilities the posterior is evaluated at.
    private static let grid: [Double] = (0...650).map { -3 + Double($0) * 0.02 }

    /// Estimated ability on the difficulty scale. `answers` must be newest first.
    static func estimate(from answers: [AnswerRecord]) -> Estimate {
        // The likelihood only depends on the total recency weight of right and
        // wrong answers at each level.
        var right = [Double](repeating: 0, count: 5)
        var wrong = [Double](repeating: 0, count: 5)
        for (age, answer) in answers.enumerated() {
            let level = min(max(answer.difficulty, 1), 5) - 1
            let weight = pow(0.5, Double(age) / halfLife)
            if answer.isCorrect { right[level] += weight } else { wrong[level] += weight }
        }

        let logPosterior = grid.map { ability in
            let z = (ability - priorMean) / priorStandardDeviation
            var total = -z * z / 2
            for level in 0..<5 {
                let p = probabilityCorrect(ability: ability, difficulty: level + 1)
                total += right[level] * log(p) + wrong[level] * log(1 - p)
            }
            return total
        }
        let peak = logPosterior.max() ?? 0
        let density = logPosterior.map { exp($0 - peak) }
        let mass = density.reduce(0, +)

        let mean = zip(grid, density).reduce(0) { $0 + $1.0 * $1.1 } / mass
        var cautious = grid[grid.count - 1]
        var cumulative = 0.0
        for (ability, density) in zip(grid, density) {
            cumulative += density
            if cumulative >= cautiousQuantile * mass {
                cautious = ability
                break
            }
        }
        return Estimate(ability: mean, cautiousAbility: cautious)
    }

    static func probabilityCorrect(ability: Double, difficulty: Int) -> Double {
        1 / (1 + exp(-slope * (ability - Double(difficulty))))
    }

    /// Maps ability to the 1–10 proficiency shown to the user. A score is earned
    /// once ability reaches its threshold: `topAbility` for a 10, and
    /// `abilityPerPoint` less for each point below.
    static func score(ability: Double) -> Int {
        let pointsBelowTop = ((topAbility - ability) / abilityPerPoint).rounded(.up)
        return 10 - Int(min(max(pointsBelowTop, 0), 9))
    }

    /// Lowest ability that earns `score` (1–10).
    static func threshold(score: Int) -> Double {
        topAbility - Double(10 - min(max(score, 1), 10)) * abilityPerPoint
    }

    /// Estimate, or `nil` until `minimumAnswers` have been answered.
    /// `recent` must be newest first.
    static func estimate(recent: [AnswerRecord], totalAnswered: Int) -> Estimate? {
        guard totalAnswered >= minimumAnswers else { return nil }
        return estimate(from: recent)
    }

    /// Proficiency (1–10), or `nil` until `minimumAnswers` have been answered.
    /// `recent` must be newest first.
    static func proficiency(recent: [AnswerRecord], totalAnswered: Int) -> Int? {
        estimate(recent: recent, totalAnswered: totalAnswered)?.proficiency
    }

    /// Share of questions at difficulties 1 through 5 (summing to 1) for a user of
    /// the given ability (the posterior mean). Before ability is known (`nil`) every
    /// level is equally likely.
    ///
    /// Practice stays varied and only leans toward the user's level: a level's
    /// weight is `6 - |level - target|`, where the target is the level the user
    /// answers about half right (their ability, clamped to 1–5). A target of 5 gives
    /// 10/15/20/25/30%, a target of 1 the mirror image, and a target of 3 peaks at
    /// level 3. Every level always gets at least 10%.
    static func difficultyWeights(ability: Double?) -> [Double] {
        guard let ability else { return Array(repeating: 0.2, count: 5) }
        let target = min(max(ability, 1), 5)
        let raw = (1...5).map { 6 - abs(Double($0) - target) }
        let total = raw.reduce(0, +)
        return raw.map { $0 / total }
    }
}
