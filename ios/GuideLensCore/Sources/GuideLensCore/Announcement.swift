import Foundation

/// What the app is trying to say, and how badly it needs to be heard.
///
/// Ordered deliberately: a safety utterance outranks everything, and
/// narration never interrupts an answer the user explicitly asked for.
public enum AnnouncementPriority: Int, Sendable, Comparable, CaseIterable {
    case system = 0
    case narration = 1
    case answer = 2
    case safety = 3

    public static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }
}

public struct Announcement: Sendable, Equatable {
    public let text: String
    public let priority: AnnouncementPriority
    /// Monotonic sequence number, so equal priorities keep arrival order.
    public let sequence: UInt64

    public init(text: String, priority: AnnouncementPriority, sequence: UInt64) {
        self.text = text
        self.priority = priority
        self.sequence = sequence
    }
}

/// What the speech layer should do next.
public enum AnnouncementAction: Sendable, Equatable {
    /// Speak immediately; nothing is in the way.
    case speak(Announcement)
    /// Stop what is speaking and speak this instead.
    case interrupt(Announcement)
    /// Hold it until the current utterance finishes.
    case enqueue(Announcement)
    /// Throw it away.
    case drop(Announcement)
}

/// The queue policy, separated from AVSpeechSynthesizer so it can be tested.
///
/// The rule that matters: a `safety` announcement cuts in. A blind user
/// stepping toward a pole cannot wait for a sentence about a doorway to
/// finish, and two seconds of speech is already stale by the time it ends.
public struct AnnouncementPolicy: Sendable {
    /// Narration is worth dropping rather than queueing: by the time the
    /// queue drains, the scene it describes has gone.
    public var dropsStaleNarration: Bool

    public init(dropsStaleNarration: Bool = true) {
        self.dropsStaleNarration = dropsStaleNarration
    }

    public func action(for incoming: Announcement, speaking current: Announcement?) -> AnnouncementAction {
        guard let current else { return .speak(incoming) }

        if incoming.priority == .safety {
            return .interrupt(incoming)
        }
        if incoming.priority > current.priority {
            return .interrupt(incoming)
        }
        if incoming.priority == .narration, dropsStaleNarration {
            // Never queue narration behind anything: stale narration is
            // worse than none at all.
            return .drop(incoming)
        }
        return .enqueue(incoming)
    }
}
