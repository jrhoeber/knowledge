import simd
import Testing
import UIKit
@testable import Knowledge

/// Checks the bundled question bank (`content.sqlite`).
@Suite(.serialized)
struct ContentTests {
    let content: ContentStore
    let providers: [Topic: any QuestionProvider]

    init() throws {
        content = try ContentStore.bundled()
        providers = try content.makeProviders()
    }

    private func count(_ sql: String) throws -> Int {
        try content.database.scalarInt(sql) ?? 0
    }

    // MARK: Mental Math

    @Test func mentalMathHasAtLeastTenThousandUniqueQuestions() throws {
        let total = try count("SELECT COUNT(*) FROM math_questions")
        let unique = try count("SELECT COUNT(*) FROM (SELECT DISTINCT operation, lhs, rhs FROM math_questions)")
        #expect(total >= 10_000)
        #expect(unique == total)
    }

    @Test func mentalMathCoversEveryOperationAtEveryLevel() throws {
        let provider = try #require(providers[.mentalMath])
        for level in 1...5 {
            #expect(provider.itemRanges(difficulty: level).count == MathPrompt.Operation.allCases.count)
        }
    }

    @Test func mentalMathQuestionsAreCorrectMultipleChoice() throws {
        let provider = try #require(providers[.mentalMath])
        var generator = SeededGenerator(seed: 21)
        for level in 1...5 {
            for range in provider.itemRanges(difficulty: level) {
                for _ in 0..<25 {
                    let question = try provider.makeQuestion(itemID: Int.random(in: range, using: &generator), using: &generator)
                    guard case .math(let prompt) = question.content else {
                        Issue.record("Expected a math prompt")
                        continue
                    }
                    let expected = switch prompt.operation {
                    case .addition: prompt.left + prompt.right
                    case .subtraction: prompt.left - prompt.right
                    case .multiplication: prompt.left * prompt.right
                    case .division: prompt.left / prompt.right
                    }
                    #expect(prompt.answer == expected)
                    if prompt.operation == .division { #expect(prompt.left % prompt.right == 0) }
                    #expect(question.options.count == 4)
                    #expect(Set(question.options).count == 4)
                    #expect(question.correctAnswer == NumberFormatting.string(expected))
                    #expect(question.difficulty == level)
                }
            }
        }
    }

    // MARK: Vocabulary

    @Test func vocabularyAsksEveryWordByMeaning() throws {
        let words = try count("SELECT COUNT(*) FROM vocab_words")
        #expect(words >= 30_000)
        #expect(try count("SELECT COUNT(DISTINCT word) FROM vocab_words") == words)
        #expect(try count("SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'vocab_words'") == words)
        // Every word has at least one quiz item, and items are meanings: more items than words.
        #expect(try count("""
            SELECT COUNT(*) FROM vocab_words w WHERE NOT EXISTS
            (SELECT 1 FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id WHERE s.word_id = w.id)
            """) == 0)
        let provider = try #require(providers[.vocabulary])
        #expect(provider.totalItemCount == (try count("SELECT COUNT(*) FROM vocab_items")))
        #expect(provider.totalItemCount > words)
    }

    /// The 3,000 most common words are never asked on their main meaning, which nearly
    /// everyone knows, only on later ones (table: to postpone; bill: a proposed law).
    @Test func commonWordsAreAskedOnlyOnLaterMeanings() throws {
        func items(_ condition: String) throws -> Int {
            try count("""
                SELECT COUNT(*) FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
                JOIN vocab_words w ON w.id = s.word_id WHERE \(condition)
                """)
        }
        #expect(try items("w.frequency_rank <= 3000 AND s.sense_order = 0") == 0)
        #expect(try items("w.frequency_rank <= 3000") > 1_000)
        #expect(try items("w.word = 'table' AND s.gloss LIKE '%postpone%'") == 1)
        #expect(try items("w.word = 'bill' AND s.gloss LIKE '%law%'") == 1)
        #expect(try items("w.word = 'bill' AND s.gloss LIKE '%beak%'") == 0)
    }

    @Test func meaningsThatRestateAMoreCommonWordAreNotAsked() throws {
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('unmusical', 'dreariness', 'shoeless')") == 0)
    }

    /// Wiktionary keeps some definitions under the British spelling (plough, jewellery)
    /// and writes others in it ("an achromatic colour"); the bank uses American spelling.
    @Test func vocabularyUsesAmericanSpelling() throws {
        let british = "'plough', 'jewellery', 'theatre', 'tyre', 'cheque', 'aluminium', 'labour', 'favourite', 'neighbour', 'defence', 'colour', 'centre', 'grey'"
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN (\(british))") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('plow', 'jewelry', 'aluminum', 'neighbor', 'favorite')") == 5)
        for spelling in ["colour", "behaviour", "centre", "travelling", "organisation", "jewellery"] {
            #expect(try count("""
                SELECT COUNT(*) FROM vocab_senses WHERE ' ' || lower(gloss) || ' ' || lower(coalesce(example, '')) || ' '
                GLOB '*[^a-z]\(spelling)[^a-z]*'
                """) == 0, "\(spelling) in a definition or example")
        }
        // Spellings that are also American stay as they are.
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('dialogue', 'axe')") == 2)
    }

    /// Words that used to drop out because of how Wiktionary files them: a definition
    /// too long for a quiz option (journalism), a page-wide slur category (peaceful), a
    /// spaced or accented headword (healthcare, cliche), a synonym-only definition
    /// (mariner), or a derogatory label on an everyday insult (idiot).
    @Test func wellKnownWordsAreNotLostToDictionaryFormatting() throws {
        let words = "'journalism', 'cheetah', 'peaceful', 'authoritarianism', 'healthcare', 'cliche', 'mariner', 'idiot', 'superstition', 'center'"
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN (\(words))") == 10)
        // Insults aimed at a group stay out even though plain insults are in.
        #expect(try count("SELECT COUNT(*) FROM vocab_words WHERE word IN ('gringo', 'spinster', 'midget', 'hick')") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_senses WHERE length(gloss) > 220") == 0)
        #expect(try count("SELECT COUNT(*) FROM vocab_senses WHERE gloss LIKE '%, particularly'") == 0)
    }

    @Test func vocabularyLevelsAreEqualFifths() throws {
        let provider = try #require(providers[.vocabulary])
        let total = Double(provider.totalItemCount)
        for level in 1...5 {
            let share = Double(provider.itemCount(difficulty: level)) / total
            #expect(abs(share - 0.2) < 0.005, "level \(level) holds \(share)")
        }
    }

    @Test func newWordsFavorTheMostCommonInTheirLevel() throws {
        let provider = try #require(providers[.vocabulary])
        let range = try #require(provider.itemRanges(difficulty: 5).first)
        let quarter = range.count / 4
        var generator = SeededGenerator(seed: 11)
        let draws = (0..<4_000).map { _ in provider.randomItem(in: range, using: &generator) }
        #expect(draws.allSatisfy(range.contains))
        let first = Double(draws.filter { $0 < range.lowerBound + quarter }.count) / Double(draws.count)
        let last = Double(draws.filter { $0 > range.upperBound - quarter }.count) / Double(draws.count)
        #expect(abs(first - 0.5) < 0.05, "first quarter share \(first)")
        #expect(last > 0.08, "rare words should still come up; last quarter share \(last)")
        #expect(CommonFirstSampler.item(in: 10...19, unit: 0) == 10)
        #expect(CommonFirstSampler.item(in: 10...19, unit: 0.999_999) == 19)
    }

    /// Difficulty follows how widely a meaning is known, not how common the word is:
    /// "photosynthesis" is rarer than "panacea" in print but far better known.
    @Test func difficultyFollowsHowWidelyAMeaningIsKnown() throws {
        func easiestLevel(_ word: String) throws -> Int {
            try count("""
                SELECT MIN(i.difficulty) FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
                JOIN vocab_words w ON w.id = s.word_id WHERE w.word = '\(word)'
                """)
        }
        func rank(_ word: String) throws -> Int {
            try count("SELECT frequency_rank FROM vocab_words WHERE word = '\(word)'")
        }
        #expect(try rank("photosynthesis") > rank("panacea"))
        #expect(try easiestLevel("photosynthesis") < easiestLevel("panacea"))
        #expect(try easiestLevel("denominator") < easiestLevel("lugubrious"))
        #expect(try easiestLevel("lugubrious") == 5)
    }

    @Test func aWordsMeaningsCanSitAtDifferentLevels() throws {
        #expect(try count("""
            SELECT COUNT(*) FROM (SELECT s.word_id FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id
            GROUP BY s.word_id HAVING COUNT(DISTINCT i.difficulty) > 1)
            """) > 1_000)
    }

    @Test("Vocabulary questions show one correct definition and three from other words", arguments: 1...5)
    func vocabularyQuestionsAreFair(level: Int) throws {
        let provider = try #require(providers[.vocabulary])
        let range = try #require(provider.itemRanges(difficulty: level).first)
        var generator = SeededGenerator(seed: UInt64(level * 1_000))
        for _ in 0..<150 {
            let itemID = Int.random(in: range, using: &generator)
            let question = try provider.makeQuestion(itemID: itemID, using: &generator)
            guard case .vocabulary(let prompt) = question.content else {
                Issue.record("Expected a vocabulary prompt")
                continue
            }
            let definitions = Set(prompt.meanings.map(\.definition))
            #expect(question.difficulty == level)
            #expect(question.options.count == 4)
            #expect(Set(question.options).count == 4)
            // The correct option is the item's own meaning.
            let tested = try #require(try content.database.queryFirst(
                "SELECT s.gloss FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id WHERE i.id = ?",
                [.int(itemID)]
            ) { $0.string(0) })
            #expect(question.correctAnswer == tested)
            #expect(definitions.contains(question.correctAnswer))
            let wrong = question.options.enumerated().filter { $0.offset != question.correctIndex }.map(\.element)
            #expect(wrong.allSatisfy { !definitions.contains($0) }, "\(prompt.word): \(wrong)")
            #expect(!prompt.meanings.isEmpty && prompt.meanings.count <= 6)
        }
    }

    @Test func overlapFilterRejectsSynonymsAndSharedRoots() {
        let filter = OverlapFilter(word: "big", related: ["large", "huge"], glosses: ["Of great size, large"])
        #expect(!filter.allows(word: "huge", related: [], gloss: "Extremely sizable"))
        #expect(!filter.allows(word: "vast", related: [], gloss: "Very large in extent"))
        #expect(!filter.allows(word: "tiny", related: ["big"], gloss: "Very small"))
        #expect(filter.allows(word: "quiet", related: [], gloss: "Making little noise"))
    }

    // MARK: Geography

    /// 193 UN members plus Vatican City, Palestine and Taiwan, and the 50 states. Capital
    /// questions skip answers that give themselves away (Mexico City, Tunis, Indianapolis)
    /// and places without an uncontested capital (Palestine, Nauru).
    @Test func geographyCoversEveryCountryAndState() throws {
        let expected = ["country_map": 196, "country_flag": 196, "state_map": 50, "country_capital": 180, "state_capital": 48]
        for (kind, total) in expected {
            #expect(try count("SELECT COUNT(*) FROM geo_items WHERE kind = '\(kind)'") == total, "\(kind)")
        }
        #expect(try count("SELECT COUNT(*) FROM geo_regions WHERE layer = 'world' AND quizzable = 1") == 196)
        #expect(try count("SELECT COUNT(*) FROM geo_regions WHERE layer = 'states' AND quizzable = 1") == 50)
        #expect(try count("""
            SELECT COUNT(*) FROM geo_regions WHERE quizzable = 1 AND name IN ('Taiwan', 'Palestine', 'Vatican City')
            """) == 3)
        // Drawn for context but never asked.
        #expect(try count("SELECT COUNT(*) FROM geo_regions WHERE quizzable = 0 AND code IN ('KOS', 'GRL', 'DC')") == 3)
        let provider = try #require(providers[.geography])
        #expect(provider.totalItemCount == (try count("SELECT COUNT(*) FROM geo_items")))
    }

    /// Western Sahara is part of Morocco and Abkhazia part of Georgia (US recognition),
    /// so neither is a separate shape; Kosovo, which the US recognizes, is.
    @Test func mapBordersFollowUSPolicy() throws {
        #expect(try count("SELECT COUNT(*) FROM geo_regions WHERE code IN ('SAH', 'B35', 'B37', 'USG')") == 0)
        #expect(try count("SELECT COUNT(*) FROM geo_regions WHERE code = 'KOS' AND layer = 'world'") == 1)
    }

    @Test func geographyRotatesThroughMapsFlagsAndCapitals() throws {
        let provider = try #require(providers[.geography])
        for level in 1...5 {
            #expect(provider.itemRanges(difficulty: level).count == 3)
        }
        for kind in ["country_map", "country_flag", "state_map", "country_capital", "state_capital"] {
            let sizes = try content.database.query(
                "SELECT COUNT(*) FROM geo_items WHERE kind = ? GROUP BY difficulty", [.text(kind)]
            ) { $0.int(0) }
            #expect(sizes.count == 5 && sizes.max()! - sizes.min()! <= 1, "\(kind): \(sizes)")
        }
    }

    @Test func capitalQuestionsNeverGiveAwayTheAnswer() throws {
        let pairs = try content.database.query("""
            SELECT r.name, r.capital FROM geo_items i JOIN geo_regions r ON r.id = i.region_id
            WHERE i.category = 'capital'
            """) { (name: $0.string(0).lowercased(), capital: $0.string(1).lowercased()) }
        for pair in pairs {
            #expect(!pair.capital.contains(pair.name) && !pair.name.contains(pair.capital), "\(pair)")
        }
        #expect(try count("""
            SELECT COUNT(*) FROM geo_items i JOIN geo_regions r ON r.id = i.region_id
            WHERE i.category = 'capital' AND r.code IN ('MEX', 'TUN', 'IN', 'OK', 'PSX', 'NRU')
            """) == 0)
    }

    @Test("Geography questions have four distinct options and one right answer", arguments: 1...5)
    func geographyQuestionsAreFair(level: Int) throws {
        let provider = try #require(providers[.geography] as? GeographyProvider)
        var generator = SeededGenerator(seed: UInt64(level * 77))
        for range in provider.itemRanges(difficulty: level) {
            for itemID in range {
                let question = try provider.makeQuestion(itemID: itemID, using: &generator)
                #expect(question.difficulty == level)
                #expect(question.options.count == 4)
                #expect(Set(question.options).count == 4)
                switch question.content {
                case .map(let prompt):
                    #expect(question.correctAnswer == prompt.target.name)
                    #expect(prompt.optionRegionIDs.count == 4)
                    let layers = prompt.optionRegionIDs.compactMap { prompt.atlas.region($0)?.layer }
                    #expect(layers == Array(repeating: prompt.layer, count: 4))
                    #expect(prompt.optionRegionIDs[question.correctIndex] == prompt.target.id)
                case .flag(let prompt):
                    #expect(question.correctAnswer == prompt.countryName)
                    #expect(prompt.optionFlags.count == 4)
                    #expect(prompt.optionFlags[question.correctIndex] == prompt.flag)
                case .capital(let prompt):
                    #expect(question.correctAnswer == prompt.capital)
                    #expect(!question.options.contains(prompt.placeName))
                default:
                    Issue.record("Expected a geography prompt")
                }
            }
        }
    }

    /// At level 5, a map's wrong answers are its neighbors and a flag's are lookalikes.
    @Test func hardQuestionsUseNearbyPlacesAndLookalikeFlags() throws {
        let provider = try #require(providers[.geography] as? GeographyProvider)
        var generator = SeededGenerator(seed: 5)
        var checked = 0
        for range in provider.itemRanges(difficulty: 5) {
            for itemID in range.prefix(25) {
                let question = try provider.makeQuestion(itemID: itemID, using: &generator)
                let (regionID, relation): (Int, String) = switch question.content {
                case .map(let prompt): (prompt.target.id, "neighbor")
                case .flag:
                    (try #require(try content.database.scalarInt(
                        "SELECT region_id FROM geo_items WHERE id = ?", [.int(itemID)]
                    )), "lookalike")
                default: (-1, "")
                }
                guard regionID > 0 else { continue }
                let near = Set(try content.database.query(
                    "SELECT o.name FROM geo_related g JOIN geo_regions o ON o.id = g.other_id WHERE g.region_id = ? AND g.relation = ?",
                    [.int(regionID), .text(relation)]
                ) { $0.string(0) })
                let wrong = question.options.enumerated().filter { $0.offset != question.correctIndex }.map(\.element)
                #expect(wrong.filter(near.contains).count >= 2, "\(question.correctAnswer): \(wrong)")
                checked += 1
            }
        }
        #expect(checked >= 40)
    }

    /// From level 3, a capital question includes one famous city that is not the
    /// capital when the place has one (Sydney for Australia, Chicago for Illinois).
    @Test func harderCapitalQuestionsIncludeADecoyCity() throws {
        let provider = try #require(providers[.geography] as? GeographyProvider)
        let rows = try content.database.query("""
            SELECT i.id, group_concat(d.city, '|') FROM geo_items i JOIN geo_decoys d ON d.region_id = i.region_id
            WHERE i.category = 'capital' AND i.difficulty >= 3 GROUP BY i.id
            """) { (id: $0.int(0), decoys: Set($0.string(1).split(separator: "|").map(String.init))) }
        #expect(rows.count >= 15)
        var generator = SeededGenerator(seed: 9)
        for row in rows {
            let question = try provider.makeQuestion(itemID: row.id, using: &generator)
            #expect(question.options.filter(row.decoys.contains).count == 1, "\(question.options)")
        }
    }

    @Test func everyFlagDecodesAtItsStoredSize() throws {
        let flags = try content.database.query("SELECT image, width, height FROM geo_flags") {
            (data: $0.data(0), width: $0.int(1), height: $0.int(2))
        }
        #expect(flags.count == 196)
        for flag in flags {
            let image = try #require(UIImage(data: flag.data))
            #expect(Int(image.size.width * image.scale) == flag.width)
            #expect(Int(image.size.height * image.scale) == flag.height)
        }
    }

    @Test func everyPlaceHasAShapeAndAFrameThatShowsIt() throws {
        let provider = try #require(providers[.geography] as? GeographyProvider)
        let atlas = try provider.atlas()
        let size = CGSize(width: 360, height: 240)
        for region in atlas.regions {
            let fine = try #require(atlas.shape(region.id, detail: .fine), "\(region.code)")
            let coarse = try #require(atlas.shape(region.id, detail: .coarse), "\(region.code)")
            #expect(!fine.rings.isEmpty && !coarse.rings.isEmpty, "\(region.code)")
            guard region.isQuizzable else { continue }
            let camera = MapCamera.zoomed(on: region, zoom: 0, size: size)
            #expect(camera.radius >= region.minimumRadius)
            // The label sits on screen in the close-up.
            let (label, isFront) = camera.project(region.label)
            #expect(isFront && CGRect(origin: .zero, size: size).contains(label), "\(region.name) label at \(label)")
        }
    }

    /// Zooming out keeps a country centered and ends on the whole globe; a state
    /// zooms out to the lower 48.
    @Test func zoomingOutShowsTheGlobeOrTheLowerFortyEight() throws {
        let provider = try #require(providers[.geography] as? GeographyProvider)
        let atlas = try provider.atlas()
        let size = CGSize(width: 360, height: 240)
        let laos = try #require(atlas.regions.first { $0.code == "LAO" })
        let close = MapCamera.zoomed(on: laos, zoom: 0, size: size)
        let far = MapCamera.zoomed(on: laos, zoom: 1, size: size)
        #expect(close.radius < 0.2 && far.radius > 1)
        #expect(simd_distance(close.center, far.center) < 1e-9)
        #expect(far.visibleAngle == .pi / 2)

        let kansas = try #require(atlas.regions.first { $0.layer == .states && $0.code == "KS" })
        let states = MapCamera.zoomed(on: kansas, zoom: 1, size: size)
        for city in [(-122.4, 37.8), (-71.1, 42.4), (-80.2, 25.8), (-122.3, 47.6)] {  // SF, Boston, Miami, Seattle
            let (point, isFront) = states.project(unitVector(longitude: city.0, latitude: city.1))
            #expect(isFront && CGRect(origin: .zero, size: size).contains(point), "\(city)")
        }
        // Tiny places get a close-up of at least the minimum size, so neighbors show.
        let vatican = try #require(atlas.regions.first { $0.code == "VAT" })
        #expect(MapCamera.zoomed(on: vatican, zoom: 0, size: size).radius >= 0.045)
    }

    // MARK: Topics

    @Test func everyTopicSymbolExists() {
        for topic in Topic.allCases {
            #expect(UIImage(systemName: topic.symbolName) != nil, "\(topic.symbolName)")
        }
    }

    @Test func mentalMathGeographyAndVocabularyAreAvailable() {
        #expect(Topic.available == [.mentalMath, .geography, .vocabulary])
        #expect(Topic.comingSoon.count == 15)
        #expect(Set(providers.keys) == Set(Topic.available))
    }
}
