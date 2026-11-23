import SwiftUI
import simd

/// An orthographic view of the unit sphere fitted to a rectangle: `center` faces the
/// viewer and `radius` (in unit-sphere units) spans half the view's height.
nonisolated struct MapCamera: Equatable {
    let center: SIMD3<Double>
    let east: SIMD3<Double>
    let north: SIMD3<Double>
    let radius: Double
    let size: CGSize

    init(center: SIMD3<Double>, radius: Double, size: CGSize) {
        let center = simd_normalize(center)
        var east = simd_cross(SIMD3<Double>(0, 0, 1), center)
        if simd_length(east) < 1e-9 { east = SIMD3(0, 1, 0) }
        east = simd_normalize(east)
        self.center = center
        self.east = east
        north = simd_cross(center, east)
        self.radius = radius
        self.size = size
    }

    /// Points per unit-sphere unit.
    var scale: Double { Double(size.height) / 2 / radius }

    var aspect: Double { Double(size.width) / max(Double(size.height), 1) }

    /// Angular radius of the part of the sphere inside the view.
    var visibleAngle: Double {
        let reach = radius * (aspect * aspect + 1).squareRoot()
        return reach >= 1 ? .pi / 2 : asin(reach)
    }

    /// Screen position of a point on the sphere, and whether it faces the viewer.
    func project(_ point: SIMD3<Double>) -> (point: CGPoint, isFront: Bool) {
        (screen(x: simd_dot(point, east), y: simd_dot(point, north)), simd_dot(point, center) >= 0)
    }

    func screen(x: Double, y: Double) -> CGPoint {
        CGPoint(x: Double(size.width) / 2 + x * scale, y: Double(size.height) / 2 - y * scale)
    }

    // MARK: Framing

    /// The close-up: the region's main landmass fills about half the view, a little
    /// less for small countries (more context) and more for very large ones, so the
    /// first ring of neighbors shows.
    static func closeUpRadius(for region: GeoRegion, aspect: Double) -> Double {
        let frame = region.closeUp
        let extent = max(frame.halfWidth, frame.halfHeight)
        let padding = extent < 0.05 ? 2.3 + (0.05 - extent) * 10 : max(1.3, 2.3 - 1.8 * (extent - 0.05))
        return max(max(frame.halfWidth / aspect, frame.halfHeight) * padding, region.minimumRadius)
    }

    /// The zoomed-out view: the whole globe for countries, the lower 48 for states.
    static func contextRadius(for region: GeoRegion, aspect: Double) -> Double {
        max(region.context.halfWidth / aspect, region.context.halfHeight) * 1.1
    }

    /// Blends from the close-up (`zoom` 0) to the zoomed-out view (1), moving the
    /// center along the sphere and the scale geometrically so the zoom feels even.
    static func zoomed(on region: GeoRegion, zoom: Double, size: CGSize) -> MapCamera {
        let aspect = Double(size.width) / max(Double(size.height), 1)
        let t = min(1, max(0, zoom))
        let near = closeUpRadius(for: region, aspect: aspect)
        let far = max(contextRadius(for: region, aspect: aspect), near)
        let mixed = region.closeUp.center * (1 - t) + region.context.center * t
        let center = simd_length(mixed) > 1e-6 ? mixed : region.closeUp.center
        return MapCamera(center: center, radius: near * pow(far / near, t), size: size)
    }
}

/// A map question's map. `zoom` animates between the close-up and the zoomed-out view.
struct GeoMapView: View, Animatable {
    let prompt: MapPrompt
    var zoom: Double
    /// A wrong pick, shown in the error color once answered.
    let chosenRegionID: Int?
    let showsLabels: Bool

    var animatableData: Double {
        get { zoom }
        set { zoom = newValue }
    }

    var body: some View {
        Canvas { context, size in
            var painter = MapPainter(
                prompt: prompt,
                camera: MapCamera.zoomed(on: prompt.target, zoom: zoom, size: size),
                chosenRegionID: chosenRegionID
            )
            painter.draw(in: &context, showsLabels: showsLabels)
        }
    }
}

/// Draws one frame of a map: water, land, the highlighted place, borders, a marker
/// around places too small to see, and (after answering) names.
private struct MapPainter {
    let prompt: MapPrompt
    let camera: MapCamera
    let chosenRegionID: Int?

    private let center: SIMD3<Float>
    private let east: SIMD3<Float>
    private let north: SIMD3<Float>
    private let scale: CGFloat
    private let mid: CGPoint
    private let visibleAngle: Double
    /// Points closer than this (squared, in points) to the last one drawn are skipped.
    private let minStep2: CGFloat = 0.36
    private var drawn: [(region: GeoRegion, fill: Path)] = []

    init(prompt: MapPrompt, camera: MapCamera, chosenRegionID: Int?) {
        self.prompt = prompt
        self.camera = camera
        self.chosenRegionID = chosenRegionID
        center = SIMD3<Float>(camera.center)
        east = SIMD3<Float>(camera.east)
        north = SIMD3<Float>(camera.north)
        scale = CGFloat(camera.scale)
        mid = CGPoint(x: camera.size.width / 2, y: camera.size.height / 2)
        visibleAngle = camera.visibleAngle
    }

    mutating func draw(in context: inout GraphicsContext, showsLabels: Bool) {
        let accent = Topic.geography.colors
        let detail: GeoAtlas.Detail = camera.radius < 0.3 ? .fine : .coarse
        let globe = Path(ellipseIn: CGRect(x: mid.x - scale, y: mid.y - scale, width: scale * 2, height: scale * 2))
        context.fill(globe, with: .color(Palette.mapWater))

        var land = Path(), underlay = Path(), borders = Path(), target = Path(), chosen = Path()
        var targetParts: [CGRect] = []
        for region in prompt.atlas.regions {
            let isUnderlay = prompt.layer == .states && region.layer == .world && region.code == "USA"
            if prompt.layer == .world && region.layer == .states { continue }
            guard let shape = prompt.atlas.shape(region.id, detail: detail), isVisible(shape.cap) else { continue }
            var fill = Path()
            var parts: [CGRect] = []
            addFill(shape, to: &fill, parts: &parts)
            guard !fill.isEmpty else { continue }
            if region.id == prompt.target.id { targetParts = parts }
            if isUnderlay {
                // The states are drawn over the country so their borders show; the
                // country underneath fills any hairline gaps along the coast.
                underlay.addPath(fill)
                continue
            }
            if region.id == prompt.target.id {
                target.addPath(fill)
            } else if region.id == chosenRegionID {
                chosen.addPath(fill)
            } else {
                land.addPath(fill)
            }
            addStroke(shape, to: &borders)
            drawn.append((region, fill))
        }

        let eoFill = FillStyle(eoFill: true)
        context.fill(underlay, with: .color(Palette.mapLand), style: eoFill)
        context.fill(land, with: .color(Palette.mapLand), style: eoFill)
        context.fill(chosen, with: .color(Palette.error), style: eoFill)
        context.fill(target, with: .color(accent.accent), style: eoFill)
        context.stroke(borders, with: .color(Palette.mapBorder), lineWidth: 0.6)
        context.stroke(target, with: .color(accent.onContainer), lineWidth: 1.1)
        if camera.radius > 0.6 {
            context.stroke(globe, with: .color(Palette.mapBorder), lineWidth: 1)
        }

        // Rings around places too small to see at this scale (Vatican City, Tuvalu):
        // one per cluster of islands, largest cluster first.
        let markers = Self.markers(around: targetParts, in: CGRect(origin: .zero, size: camera.size))
        for ring in markers {
            context.stroke(Path(ellipseIn: ring), with: .color(accent.accent), lineWidth: 2.5)
        }
        if showsLabels {
            drawLabels(in: &context, target: target, targetParts: targetParts, marker: markers.first)
        }
    }

    /// Circles around groups of a place's on-screen parts when every part is smaller
    /// than about 12 points; empty when the place is big enough to see. Parts within
    /// 24 points share a circle, as long as the group stays under 40 points across.
    static func markers(around parts: [CGRect], in canvas: CGRect) -> [CGRect] {
        let visible = parts.filter { $0.intersects(canvas) }
        guard !visible.isEmpty, visible.allSatisfy({ max($0.width, $0.height) < 12 }) else { return [] }
        var clusters: [CGRect] = []
        for part in visible.sorted(by: { $0.width * $0.height > $1.width * $1.height }) {
            if let index = clusters.firstIndex(where: {
                $0.insetBy(dx: -24, dy: -24).intersects(part) && max($0.union(part).width, $0.union(part).height) < 40
            }) {
                clusters[index] = clusters[index].union(part)
            } else {
                clusters.append(part)
            }
        }
        return clusters.prefix(6).map { cluster in
            let radius = max(11, max(cluster.width, cluster.height) / 2 + 7)
            return CGRect(x: cluster.midX - radius, y: cluster.midY - radius, width: radius * 2, height: radius * 2)
        }
    }

    // MARK: Labels

    /// Names the target (beside its marker when it is tiny), the wrong pick, and then
    /// other places, largest first, wherever a name fits inside a place without
    /// covering the target or another name.
    private func drawLabels(in context: inout GraphicsContext, target: Path, targetParts: [CGRect], marker: CGRect?) {
        let canvas = CGRect(origin: .zero, size: camera.size).insetBy(dx: 2, dy: 2)
        var placed: [CGRect] = marker.map { [$0] } ?? []

        func pill(_ name: String, emphasized: Bool, color: Color) -> (GraphicsContext.ResolvedText, CGSize) {
            let text = context.resolve(
                Text(name)
                    .font(.system(size: emphasized ? 12 : 11, weight: emphasized ? .bold : .semibold))
                    .foregroundStyle(color)
            )
            let size = text.measure(in: CGSize(width: 220, height: 40))
            return (text, CGSize(width: size.width + 10, height: size.height + 4))
        }
        func rect(_ size: CGSize, at point: CGPoint) -> CGRect {
            CGRect(x: point.x - size.width / 2, y: point.y - size.height / 2, width: size.width, height: size.height)
        }
        func clamped(_ rect: CGRect) -> CGRect {
            var rect = rect
            rect.origin.x = min(max(rect.minX, canvas.minX), canvas.maxX - rect.width)
            rect.origin.y = min(max(rect.minY, canvas.minY), canvas.maxY - rect.height)
            return rect
        }
        func draw(_ text: GraphicsContext.ResolvedText, in rect: CGRect, fill: Color) {
            placed.append(rect)
            context.fill(Path(roundedRect: rect, cornerRadius: rect.height / 2), with: .color(fill))
            context.draw(text, at: CGPoint(x: rect.midX, y: rect.midY), anchor: .center)
        }

        // The target, always: inside it when the name fits, otherwise just above its
        // marker or its largest part, so the name never hides a small island.
        let (targetText, targetSize) = pill(prompt.target.name, emphasized: true, color: .white)
        let (labelPoint, labelIsFront) = camera.project(prompt.target.label)
        let inside = rect(targetSize, at: labelPoint)
        // Roughly fits: the name may overhang a coast a little.
        let fitsInside = labelIsFront && marker == nil && [
            CGPoint(x: inside.minX + inside.width * 0.15, y: inside.midY),
            CGPoint(x: inside.maxX - inside.width * 0.15, y: inside.midY),
            CGPoint(x: inside.midX, y: inside.minY + 2), CGPoint(x: inside.midX, y: inside.maxY - 2),
        ].allSatisfy { target.contains($0, eoFill: true) }
        let beside = marker ?? targetParts.filter { $0.intersects(canvas) }.max { $0.width * $0.height < $1.width * $1.height }
        let targetAnchor = fitsInside || beside == nil
            ? (labelIsFront ? labelPoint : CGPoint(x: target.boundingRect.midX, y: target.boundingRect.midY))
            : CGPoint(x: beside!.midX, y: beside!.minY - targetSize.height / 2 - 3)
        draw(targetText, in: clamped(rect(targetSize, at: targetAnchor)), fill: Topic.geography.colors.onContainer)

        let others = drawn
            .filter { $0.region.id != prompt.target.id }
            .filter { prompt.layer == .world || $0.region.layer == .states || $0.region.code != "USA" }
            .map { (region: $0.region, fill: $0.fill, visible: $0.fill.boundingRect.intersection(canvas)) }
            .filter { !$0.visible.isNull }
            .sorted { lhs, rhs in
                let l = lhs.region.id == chosenRegionID, r = rhs.region.id == chosenRegionID
                if l != r { return l }
                return lhs.visible.width * lhs.visible.height > rhs.visible.width * rhs.visible.height
            }
        for entry in others where placed.count < 16 {
            let isChosen = entry.region.id == chosenRegionID
            let (text, size) = isChosen
                ? pill(entry.region.name, emphasized: true, color: .white)
                : pill(entry.region.name, emphasized: false, color: Palette.inkSecondary)
            // Try the place's label point, then spots spread over its visible part.
            var spots: [CGPoint] = []
            let (point, isFront) = camera.project(entry.region.label)
            if isFront { spots.append(point) }
            for fy in [0.5, 0.25, 0.75] {
                for fx in [0.5, 0.25, 0.75] {
                    spots.append(CGPoint(x: entry.visible.minX + entry.visible.width * fx,
                                         y: entry.visible.minY + entry.visible.height * fy))
                }
            }
            let fits = spots.lazy.map { rect(size, at: $0) }.first { candidate in
                let edges = [CGPoint(x: candidate.minX + 2, y: candidate.midY), CGPoint(x: candidate.midX, y: candidate.midY),
                             CGPoint(x: candidate.maxX - 2, y: candidate.midY)]
                return canvas.contains(candidate)
                    && edges.allSatisfy { entry.fill.contains($0, eoFill: true) && !target.contains($0, eoFill: true) }
                    && !placed.contains { $0.insetBy(dx: -2, dy: -2).intersects(candidate) }
            }
            if let fits {
                draw(text, in: fits, fill: isChosen ? Palette.onErrorContainer : Palette.surface.opacity(0.88))
            } else if isChosen {
                // The wrong pick is always named, even if it is too small to hold its name.
                let spot = isFront && canvas.contains(point) ? point : CGPoint(x: entry.visible.midX, y: entry.visible.midY)
                let candidate = clamped(rect(size, at: CGPoint(x: spot.x, y: spot.y - size.height)))
                if !placed.contains(where: { $0.intersects(candidate) }) {
                    draw(text, in: candidate, fill: Palette.onErrorContainer)
                }
            }
        }
    }

    // MARK: Geometry

    private func isVisible(_ cap: SphericalCap) -> Bool {
        let between = Double(acos(max(-1, min(1, simd_dot(cap.center, center)))))
        return between - cap.radius <= visibleAngle + 0.02
    }

    private func screen(_ point: SIMD3<Float>) -> CGPoint {
        CGPoint(x: mid.x + CGFloat(simd_dot(point, east)) * scale, y: mid.y - CGFloat(simd_dot(point, north)) * scale)
    }

    /// A point behind the globe, pushed out to its edge in the same direction.
    private func limb(_ point: SIMD3<Float>) -> CGPoint? {
        let x = simd_dot(point, east), y = simd_dot(point, north)
        let length = (x * x + y * y).squareRoot()
        guard length > 1e-6 else { return nil }
        return CGPoint(x: mid.x + CGFloat(x / length) * scale, y: mid.y - CGFloat(y / length) * scale)
    }

    /// Where the edge from `a` to `b` crosses the globe's edge.
    private func horizon(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> CGPoint? {
        let da = simd_dot(a, center), db = simd_dot(b, center)
        let t = da / (da - db)
        return limb(a + (b - a) * t)
    }

    /// Adds the visible part of each ring; `parts` gets each ring's on-screen bounds.
    private func addFill(_ shape: GeoShape, to path: inout Path, parts: inout [CGRect]) {
        for ring in shape.rings where ring.points.count >= 3 && isVisible(ring.cap) {
            let points = ring.points
            guard points.contains(where: { simd_dot($0, center) >= 0 }) else { continue }
            var started = false
            var last = CGPoint.zero
            var low = CGPoint(x: CGFloat.infinity, y: CGFloat.infinity)
            var high = CGPoint(x: -CGFloat.infinity, y: -CGFloat.infinity)
            func emit(_ point: CGPoint?, force: Bool = false) {
                guard let point else { return }
                low = CGPoint(x: min(low.x, point.x), y: min(low.y, point.y))
                high = CGPoint(x: max(high.x, point.x), y: max(high.y, point.y))
                if !started {
                    path.move(to: point)
                    started = true
                    last = point
                    return
                }
                let dx = point.x - last.x, dy = point.y - last.y
                if force || dx * dx + dy * dy >= minStep2 {
                    path.addLine(to: point)
                    last = point
                }
            }
            var previous = points[points.count - 1]
            var previousFront = simd_dot(previous, center) >= 0
            for point in points {
                let front = simd_dot(point, center) >= 0
                if front != previousFront { emit(horizon(previous, point), force: true) }
                emit(front ? screen(point) : limb(point))
                previous = point
                previousFront = front
            }
            if started {
                path.closeSubpath()
                parts.append(CGRect(x: low.x, y: low.y, width: high.x - low.x, height: high.y - low.y))
            }
        }
    }

    private func addStroke(_ shape: GeoShape, to path: inout Path) {
        for ring in shape.rings where ring.points.count >= 2 && isVisible(ring.cap) {
            let points = ring.points
            let count = points.count
            let hasCuts = !ring.cuts.isEmpty
            var penDown = false
            var last = CGPoint.zero
            for index in 0..<count {
                let a = points[(index + count - 1) % count], b = points[index]
                if hasCuts && ring.cuts.contains(index) {
                    penDown = false
                    continue
                }
                let aFront = simd_dot(a, center) >= 0, bFront = simd_dot(b, center) >= 0
                guard aFront || bFront else {
                    penDown = false
                    continue
                }
                guard let start = aFront ? screen(a) : horizon(a, b),
                      let end = bFront ? screen(b) : horizon(a, b) else { continue }
                if !penDown {
                    path.move(to: start)
                    last = start
                    penDown = true
                }
                let dx = end.x - last.x, dy = end.y - last.y
                if !bFront || index == count - 1 || dx * dx + dy * dy >= minStep2 {
                    path.addLine(to: end)
                    last = end
                }
                if !bFront { penDown = false }
            }
        }
    }
}
