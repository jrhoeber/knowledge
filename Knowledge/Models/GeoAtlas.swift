import Foundation
import simd

/// Which set of shapes a map draws. State maps draw the world for context and the
/// US states on top.
nonisolated enum GeoLayer: String, Sendable {
    case world
    case states
}

/// A view of the globe: an orthographic projection centered on `center`, framing a
/// shape whose half extents on the unit sphere are `halfWidth` by `halfHeight`.
nonisolated struct MapFrame: Equatable, Sendable {
    let center: SIMD3<Double>
    let halfWidth: Double
    let halfHeight: Double
}

/// A country, territory or state as drawn on the map. Shapes live in `GeoAtlas`.
nonisolated struct GeoRegion: Equatable, Sendable, Identifiable {
    let id: Int
    let layer: GeoLayer
    let code: String
    let name: String
    let continent: String
    let subregion: String
    /// Where it is, for feedback: "Southeast Asia", "the Midwest".
    let areaName: String
    let areaKm2: Double
    let isQuizzable: Bool
    /// Point on the unit sphere where its name is drawn.
    let label: SIMD3<Double>
    /// The close-up: the main landmass, with room for neighbors added by `MapCamera`.
    let closeUp: MapFrame
    /// Smallest half height of the close-up (unit sphere), so tiny places show context.
    let minimumRadius: Double
    /// The zoomed-out view: the globe for countries, the lower 48 for states.
    let context: MapFrame
}

/// A cap on the unit sphere enclosing some points, for culling what is off screen.
nonisolated struct SphericalCap: Sendable {
    let center: SIMD3<Float>
    /// Cosine of the angular radius.
    let cosRadius: Float

    init(points: [SIMD3<Float>]) {
        var sum = SIMD3<Float>.zero
        for point in points { sum += point }
        let center = simd_length(sum) > 1e-6 ? simd_normalize(sum) : SIMD3<Float>(1, 0, 0)
        var lowest: Float = 1
        for point in points { lowest = min(lowest, simd_dot(point, center)) }
        self.center = center
        cosRadius = lowest
    }

    init(enclosing caps: [SphericalCap]) {
        var sum = SIMD3<Float>.zero
        for cap in caps { sum += cap.center }
        let center = simd_length(sum) > 1e-6 ? simd_normalize(sum) : SIMD3<Float>(1, 0, 0)
        var radius: Float = 0
        for cap in caps {
            let between = acos(max(-1, min(1, simd_dot(cap.center, center))))
            radius = max(radius, between + acos(max(-1, min(1, cap.cosRadius))))
        }
        self.center = center
        cosRadius = cos(min(radius, .pi))
    }

    /// Angular radius in radians.
    var radius: Double { Double(acos(max(-1, min(1, cosRadius)))) }
}

/// One closed outline (an outer edge or a hole) as points on the unit sphere.
nonisolated struct GeoRing: Sendable {
    let points: [SIMD3<Float>]
    /// Indexes `i` where the edge arriving at point `i` is a cut along the 180th
    /// meridian or the South Pole rather than a real border; it is filled but not stroked.
    let cuts: Set<Int>
    let cap: SphericalCap
}

nonisolated struct GeoShape: Sendable {
    let rings: [GeoRing]
    let cap: SphericalCap
}

/// Every region's shapes at two levels of detail, decoded from `geo_shapes`.
nonisolated final class GeoAtlas: Sendable {
    enum Detail: Sendable { case fine, coarse }

    let regions: [GeoRegion]
    private let index: [Int: Int]
    private let fine: [Int: GeoShape]
    private let coarse: [Int: GeoShape]

    init(regions: [GeoRegion], fine: [Int: GeoShape], coarse: [Int: GeoShape]) {
        self.regions = regions
        index = Dictionary(uniqueKeysWithValues: regions.enumerated().map { ($1.id, $0) })
        self.fine = fine
        self.coarse = coarse
    }

    func region(_ id: Int) -> GeoRegion? {
        index[id].map { regions[$0] }
    }

    func shape(_ id: Int, detail: Detail) -> GeoShape? {
        detail == .fine ? fine[id] : coarse[id]
    }

    static func load(database: SQLiteDatabase, regions: [GeoRegion]) throws -> GeoAtlas {
        var fine: [Int: GeoShape] = [:]
        var coarse: [Int: GeoShape] = [:]
        let rows = try database.query("SELECT region_id, fine, coarse FROM geo_shapes") {
            (id: $0.int(0), fine: $0.data(1), coarse: $0.data(2))
        }
        for row in rows {
            fine[row.id] = try decodeShape(row.fine)
            coarse[row.id] = try decodeShape(row.coarse)
        }
        return GeoAtlas(regions: regions, fine: fine, coarse: coarse)
    }

    enum DecodeError: Error, CustomStringConvertible {
        case truncated
        var description: String { "A map shape in the question bank is truncated." }
    }

    /// Decodes the format written by `encode_shape` in `tools/content/geography.py`:
    /// little-endian ring count, then per ring a point count and Float32 lon/lat pairs.
    static func decodeShape(_ data: Data) throws -> GeoShape {
        try data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) -> GeoShape in
            var offset = 0
            func readUInt32() throws -> Int {
                guard offset + 4 <= raw.count else { throw DecodeError.truncated }
                let value = UInt32(littleEndian: raw.loadUnaligned(fromByteOffset: offset, as: UInt32.self))
                offset += 4
                return Int(value)
            }
            func readFloat() throws -> Float {
                Float(bitPattern: UInt32(try readUInt32()))
            }
            var rings: [GeoRing] = []
            for _ in 0..<(try readUInt32()) {
                let count = try readUInt32()
                var points: [SIMD3<Float>] = []
                var lonLat: [SIMD2<Float>] = []
                points.reserveCapacity(count)
                lonLat.reserveCapacity(count)
                for _ in 0..<count {
                    let lon = try readFloat(), lat = try readFloat()
                    lonLat.append(SIMD2(lon, lat))
                    points.append(SIMD3<Float>(unitVector(longitude: Double(lon), latitude: Double(lat))))
                }
                var cuts = Set<Int>()
                for i in lonLat.indices {
                    let a = lonLat[(i + lonLat.count - 1) % lonLat.count], b = lonLat[i]
                    let meridian = abs(a.x) >= 179.999 && abs(b.x) >= 179.999
                    let pole = a.y <= -89.99 && b.y <= -89.99
                    if meridian || pole { cuts.insert(i) }
                }
                rings.append(GeoRing(points: points, cuts: cuts, cap: SphericalCap(points: points)))
            }
            return GeoShape(rings: rings, cap: SphericalCap(enclosing: rings.map(\.cap)))
        }
    }
}

nonisolated func unitVector(longitude: Double, latitude: Double) -> SIMD3<Double> {
    let lon = longitude * .pi / 180, lat = latitude * .pi / 180
    return SIMD3(cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat))
}
