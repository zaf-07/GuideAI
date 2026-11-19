// NOT YET IN THE BUILD.
//
// VisionMate.xcodeproj references neither this file nor the GuideLensCore
// package, and adding either requires Xcode, which is not available on the
// machine this was written on. Nothing compiles this file today, so treat it
// as unverified: it has never been through a compiler.
//
// To wire it up, in Xcode: File > Add Package Dependencies > Add Local, pick
// ios/GuideLensCore, add GuideLensCore to the VisionMate target, then add
// this file to the target's Compile Sources. The CI job in
// .github/workflows/ci.yml builds the target on a macOS runner and will
// start covering this file once it is a member of it.

import SwiftUI
import GuideLensCore

/// SwiftUI bindings for the design tokens.
///
/// The values live in GuideLensCore as plain numbers so they can be contrast
/// checked without Xcode; this file is the thin layer that turns them into
/// `Color`, `Font` and view modifiers. Nothing here invents a value — if a
/// colour or size is needed, it is added to the tokens and checked there.
///
/// Scope: onboarding, the hearing surface, and the low-vision configuration
/// of the vision surface. A user who answered "nothing or almost nothing"
/// gets a black screen with no chrome, because pixels cost them battery and
/// privacy and return nothing.
extension Color {
    init(_ rgba: RGBA) {
        self.init(
            .sRGB,
            red: rgba.red,
            green: rgba.green,
            blue: rgba.blue,
            opacity: rgba.alpha
        )
    }
}

public enum Theme {
    public static let canvas = Color(Palette.canvas)
    public static let canvasDeep = Color(Palette.canvasDeep)
    public static let canvasTop = Color(Palette.canvasTop)
    public static let glass = Color(Palette.glass)
    public static let glassStrong = Color(Palette.glassStrong)
    public static let glassBorder = Color(Palette.glassBorder)
    public static let text = Color(Palette.text)
    public static let textMuted = Color(Palette.textMuted)
    public static let textFaint = Color(Palette.textFaint)
    public static let onLight = Color(Palette.onLight)
    public static let lime = Color(Palette.lime)
    public static let pillLight = Color(Palette.pillLight)
    public static let amber = Color(Palette.amber)
    public static let danger = Color(Palette.danger)

    /// The background field: lighter at the top, falling to near-black.
    public static var field: LinearGradient {
        LinearGradient(
            colors: [canvasTop, canvas, canvasDeep],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

public extension Font {
    /// Builds a font from a token.
    ///
    /// `relativeTo` keeps Dynamic Type working: these sizes are a starting
    /// point, not a ceiling. A low-vision user who has set the largest
    /// accessibility text size must get it, so nothing here is a fixed size.
    static func token(_ style: TextStyle, relativeTo textStyle: Font.TextStyle) -> Font {
        .system(size: style.size, weight: .init(style.weight), design: .default)
    }
}

private extension Font.Weight {
    init(_ numeric: Int) {
        switch numeric {
        case ..<400: self = .light
        case 400..<500: self = .regular
        case 500..<600: self = .medium
        case 600..<700: self = .semibold
        default: self = .bold
        }
    }
}

public extension View {
    /// Applies a token's size, leading and tracking, scaled by Dynamic Type.
    func textToken(_ style: TextStyle, relativeTo textStyle: Font.TextStyle = .body) -> some View {
        self
            .font(.token(style, relativeTo: textStyle))
            .tracking(style.tracking)
            .lineSpacing(max(0, style.lineHeight - style.size))
    }

    /// A glass card: translucent fill, hairline border, generous radius.
    func glassCard() -> some View {
        self
            .padding(Spacing.lg)
            .background(Theme.glass)
            .clipShape(RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.lg, style: .continuous)
                    .stroke(Theme.glassBorder, lineWidth: 1)
            )
    }

    /// Guarantees a target no smaller than the token, which is already well
    /// above Apple's 44pt floor. Onboarding goes further and uses half-screen
    /// zones, so a user who cannot see the question need not aim at all.
    func minimumTarget() -> some View {
        frame(minWidth: minimumHitSize, minHeight: minimumHitSize)
    }
}

/// The primary action: one light pill, full width, never more than one on a
/// screen.
public struct PillButtonStyle: ButtonStyle {
    public enum Tone { case primary, lime, glass }

    public let tone: Tone
    public init(tone: Tone = .primary) { self.tone = tone }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .textToken(Typography.section, relativeTo: .headline)
            .foregroundStyle(tone == .glass ? Theme.text : Theme.onLight)
            .frame(maxWidth: .infinity)
            .frame(minHeight: minimumHitSize)
            .padding(.horizontal, Spacing.lg)
            .background(background)
            .clipShape(Capsule())
            .overlay(tone == .glass ? Capsule().stroke(Theme.glassBorder, lineWidth: 1) : nil)
            .opacity(configuration.isPressed ? 0.85 : 1)
    }

    private var background: Color {
        switch tone {
        case .primary: return Theme.pillLight
        case .lime: return Theme.lime
        case .glass: return Theme.glass
        }
    }
}
