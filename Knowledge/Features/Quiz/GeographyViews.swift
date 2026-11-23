import SwiftUI
import UIKit

/// A map question: the map, with a control to zoom out for context.
struct MapPromptCard: View {
    let prompt: MapPrompt
    let outcome: QuizEngine.Outcome?
    @State private var zoomedOut = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            Text(prompt.question)
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(Palette.ink)
            GeoMapView(prompt: prompt, zoom: zoomedOut ? 1 : 0, chosenRegionID: chosenRegionID, showsLabels: outcome != nil)
                .aspectRatio(3 / 2, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: Radius.medium, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.medium, style: .continuous)
                        .strokeBorder(Palette.outline, lineWidth: 1)
                )
                .contentShape(Rectangle())
                .onTapGesture { zoomedOut.toggle() }
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.7), value: zoomedOut)
                .accessibilityIdentifier("mapView")
            Picker("Map zoom", selection: $zoomedOut) {
                Text("Close-up").tag(false)
                Text("Zoomed out").tag(true)
            }
            .pickerStyle(.segmented)
            .controlSize(.large)
            .accessibilityIdentifier("mapZoomPicker")
        }
        .padding(Spacing.l)
        .cardSurface(radius: Radius.large)
    }

    private var chosenRegionID: Int? {
        guard let outcome, !outcome.isCorrect, prompt.optionRegionIDs.indices.contains(outcome.selectedIndex) else {
            return nil
        }
        return prompt.optionRegionIDs[outcome.selectedIndex]
    }
}

/// A flag question: the flag at its true proportions.
struct FlagPromptCard: View {
    let prompt: FlagPrompt

    var body: some View {
        VStack(spacing: Spacing.l) {
            Text("Which country's flag is this?")
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(Palette.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
            FlagView(flag: prompt.flag)
                .frame(maxWidth: 300, maxHeight: 190)
                .padding(.vertical, Spacing.s)
                .accessibilityIdentifier("flagImage")
        }
        .padding(Spacing.l)
        .cardSurface(radius: Radius.large)
    }
}

/// A flag image with a hairline edge, so white flags stand out from the card.
struct FlagView: View {
    let flag: FlagImage

    var body: some View {
        if let image = UIImage(data: flag.data) {
            let isRectangular = image.cgImage.map { [.none, .noneSkipFirst, .noneSkipLast].contains($0.alphaInfo) } ?? true
            Image(uiImage: image)
                .resizable()
                .interpolation(.high)
                .aspectRatio(flag.aspectRatio, contentMode: .fit)
                .overlay {
                    if isRectangular {
                        Rectangle().strokeBorder(Palette.ink.opacity(0.14), lineWidth: 1)
                    }
                }
        } else {
            Rectangle()
                .fill(Palette.surfaceMuted)
                .aspectRatio(flag.aspectRatio, contentMode: .fit)
        }
    }
}

/// After a wrong flag answer: the flag that was picked beside the right one.
struct FlagComparisonCard: View {
    let prompt: FlagPrompt
    let chosenIndex: Int
    let chosenName: String

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            Text("Tell them apart")
                .font(.system(.headline, design: .rounded, weight: .bold))
                .foregroundStyle(Palette.ink)
            HStack(alignment: .top, spacing: Spacing.l) {
                column(flag: prompt.optionFlags[chosenIndex], name: chosenName, caption: "Your answer",
                       tint: Palette.onErrorContainer)
                column(flag: prompt.flag, name: prompt.countryName, caption: "This flag", tint: Palette.onSuccessContainer)
            }
        }
        .padding(Spacing.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface(radius: Radius.large)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("flagComparisonCard")
    }

    private func column(flag: FlagImage, name: String, caption: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            FlagView(flag: flag)
                .frame(maxWidth: .infinity, maxHeight: 90, alignment: .leading)
            Text(caption)
                .font(.system(.footnote, design: .rounded, weight: .semibold))
                .foregroundStyle(tint)
            Text(name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A short fact shown after answering, such as a country's second capital.
struct GeographyNoteCard: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Text(title)
                .font(.system(.headline, design: .rounded, weight: .bold))
                .foregroundStyle(Topic.geography.colors.onContainer)
            Text(text)
                .font(.body)
                .foregroundStyle(Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(Spacing.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: Radius.large, style: .continuous)
                .fill(Topic.geography.colors.container)
        )
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("geographyNoteCard")
    }
}
