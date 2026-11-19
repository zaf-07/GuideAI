import Foundation

/// Decides when a frame is worth sending for narration.
///
/// This is a latency decision, a cost decision, and above all what makes the
/// app bearable to listen to. A user standing still generates no calls at
/// all: there is nothing new to say, and saying it anyway is the top
/// complaint about assistive vision apps.
public struct MotionGate: Sendable {
    public enum Verbosity: Sendable {
        /// "Only when it matters."
        case sparse
        /// "Describe as I walk."
        case continuous

        public var interval: Double {
            switch self {
            case .sparse: return 6.0
            case .continuous: return 2.0
            }
        }
    }

    public struct Pose: Sendable {
        public let x: Double
        public let z: Double
        /// Radians.
        public let heading: Double
        public init(x: Double, z: Double, heading: Double) {
            self.x = x
            self.z = z
            self.heading = heading
        }
    }

    public var verbosity: Verbosity
    public var headingThreshold: Double
    public var distanceThreshold: Double

    private var lastSent: (pose: Pose, time: Double)?

    public init(
        verbosity: Verbosity = .sparse,
        headingThreshold: Double = 15.0 * .pi / 180.0,
        distanceThreshold: Double = 1.5
    ) {
        self.verbosity = verbosity
        self.headingThreshold = headingThreshold
        self.distanceThreshold = distanceThreshold
    }

    /// `userRequested` always wins: an explicit tap is never gated.
    public mutating func shouldSend(
        pose: Pose,
        now: Double,
        moving: Bool,
        userRequested: Bool = false
    ) -> Bool {
        if userRequested {
            lastSent = (pose, now)
            return true
        }
        guard let last = lastSent else {
            lastSent = (pose, now)
            return true
        }

        let turned = abs(angleDelta(pose.heading, last.pose.heading)) > headingThreshold
        let travelled = hypot(pose.x - last.pose.x, pose.z - last.pose.z) > distanceThreshold
        // The interval only applies while moving, so standing still is silent
        // however long the user stands there.
        let overdue = moving && (now - last.time) >= verbosity.interval

        guard turned || travelled || overdue else { return false }
        lastSent = (pose, now)
        return true
    }

    public mutating func reset() { lastSent = nil }

    /// Shortest signed angle between two headings, so 359° and 1° are 2° apart.
    private func angleDelta(_ a: Double, _ b: Double) -> Double {
        var delta = (a - b).truncatingRemainder(dividingBy: 2 * .pi)
        if delta > .pi { delta -= 2 * .pi }
        if delta < -.pi { delta += 2 * .pi }
        return delta
    }
}
