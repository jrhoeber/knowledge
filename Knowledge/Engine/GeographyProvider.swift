import Foundation

/// Geography questions: name a highlighted country or US state, name the country a
/// flag belongs to, or pick the capital of a country or state.
///
/// Items are grouped in three categories (maps, flags, capitals) with contiguous IDs
/// per category and difficulty, so the engine rotates through them evenly. Wrong
/// answers come from the same layer (countries for countries, states for states) and
/// get closer as the level rises: other continents (or Census regions) at level 1,
/// the same continent at level 3, and neighbors, lookalike flags or famous
/// non-capital cities at level 5.
final class GeographyProvider: QuestionProvider {
    let topic = Topic.geography

    enum Kind: String {
        case countryMap = "country_map"
        case stateMap = "state_map"
        case countryFlag = "country_flag"
        case countryCapital = "country_capital"
        case stateCapital = "state_capital"
    }

    /// Facts about a quiz place beyond what the map needs.
    private struct Place {
        let region: GeoRegion
        let capital: String?
        let capitalNote: String?
        let flagNote: String?
        /// Nearest quiz places in the same layer, touching ones first.
        var neighbors: [Int] = []
        /// Countries with the most similar flags, closest first.
        var lookalikes: [Int] = []
        /// Well-known cities that are not the capital.
        var decoys: [String] = []
    }

    private struct Item {
        let kind: Kind
        let regionID: Int
        let difficulty: Int
    }

    private let database: SQLiteDatabase
    private let ranges: [Int: [ClosedRange<Int>]]
    private let regions: [GeoRegion]
    private var places: [Int: Place]
    private var loadedAtlas: GeoAtlas?

    init(database: SQLiteDatabase) throws {
        self.database = database

        let rows = try database.query(
            "SELECT difficulty, MIN(id), MAX(id), COUNT(*) FROM geo_items GROUP BY difficulty, category"
        ) { (difficulty: $0.int(0), first: $0.int(1), last: $0.int(2), count: $0.int(3)) }
        var ranges: [Int: [ClosedRange<Int>]] = [:]
        for row in rows {
            guard row.last - row.first + 1 == row.count else {
                throw QuestionProviderError.nonContiguousRange(table: "geo_items")
            }
            ranges[row.difficulty, default: []].append(row.first...row.last)
        }
        self.ranges = ranges

        var places: [Int: Place] = [:]
        regions = try database.query(
            """
            SELECT id, layer, code, name, continent, subregion, area_name, area_km2, quizzable,
                   label_lon, label_lat, frame_lon, frame_lat, frame_x, frame_y, frame_min,
                   context_lon, context_lat, context_x, context_y, capital, capital_note, flag_note
            FROM geo_regions ORDER BY id
            """
        ) { row in
            let region = GeoRegion(
                id: row.int(0),
                layer: GeoLayer(rawValue: row.string(1)) ?? .world,
                code: row.string(2),
                name: row.string(3),
                continent: row.string(4),
                subregion: row.string(5),
                areaName: row.string(6),
                areaKm2: row.double(7),
                isQuizzable: row.bool(8),
                label: unitVector(longitude: row.double(9), latitude: row.double(10)),
                closeUp: MapFrame(
                    center: unitVector(longitude: row.double(11), latitude: row.double(12)),
                    halfWidth: row.double(13), halfHeight: row.double(14)
                ),
                minimumRadius: row.double(15),
                context: MapFrame(
                    center: unitVector(longitude: row.double(16), latitude: row.double(17)),
                    halfWidth: row.double(18), halfHeight: row.double(19)
                )
            )
            if region.isQuizzable {
                places[region.id] = Place(
                    region: region, capital: row.optionalString(20).flatMap { $0.isEmpty ? nil : $0 },
                    capitalNote: row.optionalString(21).flatMap { $0.isEmpty ? nil : $0 },
                    flagNote: row.optionalString(22).flatMap { $0.isEmpty ? nil : $0 }
                )
            }
            return region
        }
        let related = try database.query(
            "SELECT region_id, relation, other_id FROM geo_related ORDER BY region_id, relation, rank"
        ) { (id: $0.int(0), relation: $0.string(1), other: $0.int(2)) }
        for row in related {
            if row.relation == "neighbor" {
                places[row.id]?.neighbors.append(row.other)
            } else {
                places[row.id]?.lookalikes.append(row.other)
            }
        }
        let decoys = try database.query("SELECT region_id, city FROM geo_decoys ORDER BY rowid") {
            (id: $0.int(0), city: $0.string(1))
        }
        for row in decoys {
            places[row.id]?.decoys.append(row.city)
        }
        self.places = places
    }

    func itemRanges(difficulty: Int) -> [ClosedRange<Int>] {
        ranges[difficulty] ?? []
    }

    /// Shapes are decoded on the first map question.
    func atlas() throws -> GeoAtlas {
        if let loadedAtlas { return loadedAtlas }
        let atlas = try GeoAtlas.load(database: database, regions: regions)
        loadedAtlas = atlas
        return atlas
    }

    func makeQuestion(itemID: Int, using generator: inout SeededGenerator) throws -> Question {
        guard let item = try database.queryFirst(
            "SELECT kind, region_id, difficulty FROM geo_items WHERE id = ?", [.int(itemID)], map: { row in
                Kind(rawValue: row.string(0)).map { Item(kind: $0, regionID: row.int(1), difficulty: row.int(2)) }
            }
        ) ?? nil, let place = places[item.regionID] else {
            throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
        }

        let content: Question.Content
        let answer: String
        var options: [String]
        switch item.kind {
        case .countryMap, .stateMap:
            let others = distractors(for: place, difficulty: item.difficulty, near: place.neighbors,
                                     label: \.region.name, using: &generator)
            let chosen = ([place] + others).shuffled(using: &generator)
            answer = place.region.name
            options = chosen.map(\.region.name)
            content = .map(MapPrompt(
                atlas: try atlas(), layer: place.region.layer, target: place.region,
                optionRegionIDs: chosen.map(\.region.id)
            ))
        case .countryFlag:
            let others = distractors(for: place, difficulty: item.difficulty, near: place.lookalikes,
                                     label: \.region.name, using: &generator)
            let chosen = ([place] + others).shuffled(using: &generator)
            let flags = try loadFlags(chosen.map(\.region.id))
            guard let flag = flags[place.region.id], chosen.allSatisfy({ flags[$0.region.id] != nil }) else {
                throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
            }
            answer = place.region.name
            options = chosen.map(\.region.name)
            content = .flag(FlagPrompt(
                countryName: place.region.name, flag: flag,
                optionFlags: chosen.compactMap { flags[$0.region.id] }, note: place.flagNote
            ))
        case .countryCapital, .stateCapital:
            guard let capital = place.capital else {
                throw QuestionProviderError.missingItem(topic: topic, itemID: itemID)
            }
            var cities = distractors(for: place, difficulty: item.difficulty, near: place.neighbors,
                                     label: { $0.capital ?? "" }, using: &generator)
                .compactMap(\.capital)
            // From level 3, one wrong answer is a famous city that is not the capital.
            if item.difficulty >= 3, let decoy = place.decoys
                .filter({ $0 != capital && !cities.contains($0) })
                .randomElement(using: &generator), !cities.isEmpty {
                cities[cities.count - 1] = decoy
            }
            answer = capital
            options = ([capital] + cities).shuffled(using: &generator)
            content = .capital(CapitalPrompt(
                placeName: place.region.name, isState: item.kind == .stateCapital, capital: capital,
                note: place.capitalNote
            ))
        }

        guard options.count == 4, Set(options).count == 4, let correctIndex = options.firstIndex(of: answer) else {
            throw QuestionProviderError.notEnoughOptions(topic: topic, itemID: itemID)
        }
        return Question(
            topic: topic, itemID: itemID, difficulty: item.difficulty, content: content,
            options: options, correctIndex: correctIndex
        )
    }

    // MARK: Distractors

    /// Three other quiz places from the target's layer whose `label` (name or capital)
    /// is distinct and non-empty, drawn closer to the target as `difficulty` rises.
    private func distractors(
        for target: Place, difficulty: Int, near: [Int], label: (Place) -> String,
        using generator: inout SeededGenerator
    ) -> [Place] {
        let pool = places.values
            .filter { $0.region.layer == target.region.layer && $0.region.id != target.region.id && !label($0).isEmpty }
            .sorted { $0.region.id < $1.region.id }
        let close = near.prefix(6).compactMap { id in pool.first { $0.region.id == id } }
        let sameContinent = pool.filter { $0.region.continent == target.region.continent }
        let elsewhere = pool.filter { $0.region.continent != target.region.continent }

        let plan: [([Place], Int)] = switch difficulty {
        case 1: [(elsewhere, 3)]
        case 2: [(sameContinent, 1), (elsewhere, 2)]
        case 3: [(sameContinent, 2), (close, 1)]
        case 4: [(close, 2), (sameContinent, 1)]
        default: [(close, 3)]
        }

        var chosen: [Place] = []
        var labels: Set<String> = [label(target)]
        func take(from source: [Place], count: Int, using generator: inout SeededGenerator) {
            var added = 0
            for place in source.shuffled(using: &generator) where added < count && chosen.count < 3 {
                let text = label(place)
                guard !labels.contains(text) else { continue }
                labels.insert(text)
                chosen.append(place)
                added += 1
            }
        }
        for (source, count) in plan {
            take(from: source, count: count, using: &generator)
        }
        // Fill any shortfall (a lonely island has few neighbors) from nearby, then anywhere.
        take(from: close + sameContinent, count: 3, using: &generator)
        take(from: pool, count: 3, using: &generator)
        return chosen
    }

    // MARK: Flags

    private func loadFlags(_ ids: [Int]) throws -> [Int: FlagImage] {
        let placeholders = Array(repeating: "?", count: ids.count).joined(separator: ",")
        let rows = try database.query(
            "SELECT region_id, image, width, height FROM geo_flags WHERE region_id IN (\(placeholders))",
            ids.map(SQLiteValue.int)
        ) { (id: $0.int(0), flag: FlagImage(data: $0.data(1), width: $0.int(2), height: $0.int(3))) }
        return Dictionary(uniqueKeysWithValues: rows.map { ($0.id, $0.flag) })
    }
}
