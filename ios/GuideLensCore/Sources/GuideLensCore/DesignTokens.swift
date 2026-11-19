import Foundation

/// The visual language carried over from the React Native client: a deep
/// forest-green field, soft dark glass cards, a single light pill as the
/// primary action, and a lime accent.
///
/// Held here as plain numbers rather than SwiftUI `Color` values for two
/// reasons. It keeps the package free of UI frameworks, so it still builds
/// without Xcode. And it makes contrast a thing that can be *checked* rather
/// than eyeballed — which matters more here than in an ordinary app, because
/// a low-vision user's ability to read a screen is the feature.
///
/// Note where this design does and does not apply. Onboarding, the hearing
/// surface and the low-vision configuration are rendered with these tokens.
/// The vision surface for a user who answered "nothing or almost nothing"
/// renders black and draws no chrome at all: pixels there cost battery and
/// privacy and buy that user nothing.
public struct RGBA: Sendable, Equatable {
    public let red: Double
    public let green: Double
    public let blue: Double
    public let alpha: Double

    public init(red: Double, green: Double, blue: Double, alpha: Double = 1) {
        self.red = red
        self.green = green
        self.blue = blue
        self.alpha = alpha
    }

    /// `0xRRGGBB`, matching the hex values the design was authored in.
    public init(hex: UInt32, alpha: Double = 1) {
        self.red = Double((hex >> 16) & 0xFF) / 255.0
        self.green = Double((hex >> 8) & 0xFF) / 255.0
        self.blue = Double(hex & 0xFF) / 255.0
        self.alpha = alpha
    }

    /// Flattens a translucent colour onto an opaque one.
    ///
    /// Glass surfaces are white at 9-16% opacity, so their real contrast depends
    /// entirely on what sits behind them. Checking the literal token would
    /// measure a colour no user ever sees.
    public func composited(over backdrop: RGBA) -> RGBA {
        guard alpha < 1 else { return self }
        func blend(_ top: Double, _ bottom: Double) -> Double {
            top * alpha + bottom * (1 - alpha)
        }
        return RGBA(
            red: blend(red, backdrop.red),
            green: blend(green, backdrop.green),
            blue: blend(blue, backdrop.blue),
            alpha: 1
        )
    }

    /// WCAG 2.1 relative luminance.
    public var relativeLuminance: Double {
        func channel(_ value: Double) -> Double {
            value <= 0.03928 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
    }
}

/// WCAG 2.1 contrast ratio, from 1 (identical) to 21 (black on white).
public func contrastRatio(_ a: RGBA, _ b: RGBA, over backdrop: RGBA? = nil) -> Double {
    let first = backdrop.map(a.composited(over:)) ?? a
    let second = backdrop.map(b.composited(over:)) ?? b
    let lighter = max(first.relativeLuminance, second.relativeLuminance)
    let darker = min(first.relativeLuminance, second.relativeLuminance)
    return (lighter + 0.05) / (darker + 0.05)
}

public enum Palette {
    // Backgrounds
    public static let canvas = RGBA(hex: 0x16271F)
    public static let canvasDeep = RGBA(hex: 0x07110F)
    public static let canvasTop = RGBA(hex: 0x2E4A3A)
    public static let ink = RGBA(hex: 0x07110F)

    // Glass surfaces. Translucent by design; always check them composited.
    public static let glass = RGBA(red: 1, green: 1, blue: 1, alpha: 0.09)
    public static let glassStrong = RGBA(red: 1, green: 1, blue: 1, alpha: 0.16)
    public static let glassBorder = RGBA(red: 1, green: 1, blue: 1, alpha: 0.14)

    // Text
    public static let text = RGBA(hex: 0xFFFFFF)
    public static let textMuted = RGBA(hex: 0xC3CDC2)
    /// Raised from the client's #8E9B8D. That value cleared AA on the plain
    /// canvas at 5.4:1, but fell to 4.1:1 once a glass card sat behind it,
    /// under the 4.5:1 body-text floor — and captions and hints are exactly
    /// what sits on those cards. This measures 7.0:1 and 5.4:1.
    public static let textFaint = RGBA(hex: 0xA3B2A1)
    public static let onLight = RGBA(hex: 0x16211A)

    // Accents
    public static let lime = RGBA(hex: 0xB7FF56)
    public static let limeDeep = RGBA(hex: 0x8FD02F)
    public static let pillLight = RGBA(hex: 0xF3F2EC)
    public static let amber = RGBA(hex: 0xFFD043)
    public static let danger = RGBA(hex: 0xFF6B5E)
    public static let info = RGBA(hex: 0x8FD3FF)
}

public enum Radius {
    public static let sm: Double = 14
    public static let md: Double = 22
    public static let lg: Double = 28
    public static let xl: Double = 34
    /// Fully rounded.
    public static let pill: Double = 999
}

public enum Spacing {
    public static let xs: Double = 6
    public static let sm: Double = 10
    public static let md: Double = 16
    public static let lg: Double = 22
    public static let xl: Double = 30
    public static let xxl: Double = 42
}

/// One step of the type scale.
public struct TextStyle: Sendable, Equatable {
    public let size: Double
    public let lineHeight: Double
    public let weight: Int
    public let tracking: Double

    public init(size: Double, lineHeight: Double, weight: Int, tracking: Double = 0) {
        self.size = size
        self.lineHeight = lineHeight
        self.weight = weight
        self.tracking = tracking
    }
}

public enum Typography {
    public static let display = TextStyle(size: 42, lineHeight: 46, weight: 700, tracking: -1.2)
    public static let title = TextStyle(size: 30, lineHeight: 34, weight: 700, tracking: -0.7)
    public static let section = TextStyle(size: 21, lineHeight: 26, weight: 600, tracking: -0.3)
    public static let body = TextStyle(size: 17, lineHeight: 25, weight: 400)
    public static let label = TextStyle(size: 15, lineHeight: 20, weight: 600)
    public static let caption = TextStyle(size: 13, lineHeight: 18, weight: 500)

    /// Largest to smallest, for checking the scale holds together.
    public static let scale = [display, title, section, body, label, caption]
}

/// Minimum interactive size, deliberately well above Apple's 44pt floor.
///
/// Onboarding goes further still: its answers are half-screen tap zones, so
/// a user who cannot see the question does not have to aim at all.
public let minimumHitSize: Double = 64

/// WCAG 2.1 AA thresholds.
public enum Contrast {
    public static let bodyText: Double = 4.5
    /// 18pt+, or 14pt+ bold.
    public static let largeText: Double = 3.0
    public static let nonText: Double = 3.0

    /// Point size at which WCAG's "large text" allowance applies.
    public static func isLarge(_ style: TextStyle) -> Bool {
        style.size >= 18 || (style.size >= 14 && style.weight >= 700)
    }

    public static func required(for style: TextStyle) -> Double {
        isLarge(style) ? largeText : bodyText
    }
}
