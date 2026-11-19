import Foundation

/// Turns a token stream into speakable fragments as they arrive.
///
/// The highest-leverage trick in the app: speaking the first fragment the
/// moment it is complete, rather than waiting for the reply to finish, is
/// what turns roughly 1.5 seconds into roughly 400 milliseconds of perceived
/// latency.
public struct SentenceChunker: Sendable {
    /// Emit after this many words even with no punctuation, so a long
    /// unpunctuated reply still starts speaking promptly.
    public var wordLimit: Int
    private var buffer: String = ""

    public init(wordLimit: Int = 5) {
        self.wordLimit = wordLimit
    }

    private static let boundaries: Set<Character> = [".", ",", "!", "?", ";", ":"]

    /// Feed a streamed delta; get back any fragments ready to speak.
    public mutating func feed(_ delta: String) -> [String] {
        buffer += delta
        var ready: [String] = []

        while true {
            if let index = buffer.firstIndex(where: { Self.boundaries.contains($0) }) {
                let fragment = String(buffer[...index])
                buffer = String(buffer[buffer.index(after: index)...])
                let trimmed = fragment.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { ready.append(trimmed) }
                continue
            }
            let words = buffer.split(separator: " ", omittingEmptySubsequences: true)
            if words.count > wordLimit {
                // Keep the trailing partial word in the buffer; it may still
                // be mid-token.
                let keep = words.suffix(words.count - wordLimit).joined(separator: " ")
                let fragment = words.prefix(wordLimit).joined(separator: " ")
                buffer = buffer.hasSuffix(" ") ? keep + " " : keep
                ready.append(fragment)
                continue
            }
            break
        }
        return ready
    }

    /// Whatever is left when the stream ends.
    public mutating func flush() -> String? {
        let trimmed = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
        buffer = ""
        return trimmed.isEmpty ? nil : trimmed
    }
}
