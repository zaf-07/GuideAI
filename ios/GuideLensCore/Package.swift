// swift-tools-version: 6.0
import PackageDescription

// Every decision rule in GuideLens lives here, deliberately free of ARKit,
// PHASE, CoreHaptics and SwiftUI. Those frameworks cannot be exercised
// outside a physical device, so anything depending on them cannot be tested
// until one is in hand. Keeping the rules platform-free means the obstacle
// filter, the announcement policy and the motion gate are verifiable now,
// and the iOS app becomes a thin layer wiring sensors to proven logic.
//
// The checks are an executable rather than a test target on purpose: neither
// XCTest nor swift-testing ships with the Command Line Tools, so a test
// target cannot build without a full Xcode install. `swift run
// GuideLensChecks` needs only the toolchain, which means these rules stay
// verified on a machine that cannot install Xcode at all.
let package = Package(
    name: "GuideLensCore",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "GuideLensCore", targets: ["GuideLensCore"]),
        .executable(name: "GuideLensChecks", targets: ["GuideLensChecks"]),
    ],
    targets: [
        .target(
            name: "GuideLensCore",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .executableTarget(
            name: "GuideLensChecks",
            dependencies: ["GuideLensCore"],
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
