import Foundation

/// SplitMix64: a small, fast, seedable random number generator. The quiz engine uses
/// it everywhere so tests can replay exact question sequences from a seed.
nonisolated struct SeededGenerator: RandomNumberGenerator, Sendable {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    /// Seeds from the system generator.
    init() {
        var system = SystemRandomNumberGenerator()
        state = system.next()
    }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    /// Picks an index with probability proportional to its weight. Returns `nil`
    /// when no weight is positive.
    mutating func weightedIndex(_ weights: [Double]) -> Int? {
        let total = weights.reduce(0) { $0 + max($1, 0) }
        guard total > 0 else { return nil }
        var target = Double.random(in: 0..<total, using: &self)
        for (index, weight) in weights.enumerated() where weight > 0 {
            if target < weight { return index }
            target -= weight
        }
        return weights.lastIndex { $0 > 0 }
    }
}
