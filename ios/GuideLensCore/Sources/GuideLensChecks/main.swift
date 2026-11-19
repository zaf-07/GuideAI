import Foundation
import GuideLensCore

var checks = Checks()

// MARK: - Obstacle filter
//
// The component the product rests on. A missed low chair is recoverable; a
// phantom obstacle every twenty seconds means the user stops believing the
// app and uninstalls it.

func grid(_ cells: [Cell: Double], _ time: Double) -> DepthGrid {
    DepthGrid(cells: cells, timestamp: time)
}
func centerTorso(_ distance: Double) -> [Cell: Double] {
    [Cell(azimuth: .center, elevation: .torso): distance]
}

checks.section("Depth reduction")

var noisy = Array(repeating: 3.0, count: 100)
noisy[0] = 0.1
checks.expectClose(tenthPercentile(noisy) ?? 0, 3.0, 0.001, "one rogue pixel is noise, not an object")

var real = Array(repeating: 3.0, count: 100)
for index in 0..<15 { real[index] = 1.2 }
checks.expectClose(tenthPercentile(real) ?? 0, 1.2, 0.001, "a tenth of the cell agreeing is an object")
checks.expect(tenthPercentile([]) == nil, "no samples yields no distance")
checks.expect(tenthPercentile([0, -1, .nan, .infinity]) == nil, "invalid samples are rejected")

checks.section("Temporal confirmation")

var filter = ObstacleFilter()
checks.expect(filter.ingest(grid(centerTorso(1.0), 0)).isEmpty, "a single frame never raises an obstacle")

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(1.00), 0.0))
_ = filter.ingest(grid(centerTorso(1.02), 0.1))
var confirmed = filter.ingest(grid(centerTorso(1.01), 0.2))
checks.expectEqual(confirmed.count, 1, "three agreeing frames confirm an obstacle")
checks.expect(confirmed.first?.cell.azimuth == .center, "the obstacle keeps its direction")

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(1.0), 0.0))
_ = filter.ingest(grid(centerTorso(3.5), 0.1))
checks.expect(filter.ingest(grid(centerTorso(1.2), 0.2)).isEmpty, "frames that disagree by metres are bad depth, not an object")

filter = ObstacleFilter()
var alarms = 0
for frame in 0..<300 {
    let jitter = Double(frame % 7) * 0.01
    alarms += filter.ingest(grid([
        Cell(azimuth: .hardLeft, elevation: .torso): 6.0 + jitter,
        Cell(azimuth: .hardRight, elevation: .torso): 6.2 + jitter,
    ], Double(frame) * 0.033)).count
}
checks.expectEqual(alarms, 0, "an empty corridor raises zero alarms across 300 frames")

filter = ObstacleFilter()
alarms = 0
for frame in 0..<30 {
    let cells = frame % 2 == 0 ? centerTorso(1.0) : [:]
    alarms += filter.ingest(grid(cells, Double(frame) * 0.033)).count
}
checks.expectEqual(alarms, 0, "depth that drops out between frames is never confirmed")

filter = ObstacleFilter()
for frame in 0..<4 { _ = filter.ingest(grid(centerTorso(9.0), Double(frame) * 0.1)) }
checks.expect(filter.ingest(grid(centerTorso(9.0), 0.5)).isEmpty, "obstacles beyond range say nothing")

// Allowing steady motion through the filter must not let noise through with
// it. These are what bad depth actually looks like.
filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(2.0), 0.0))
_ = filter.ingest(grid(centerTorso(1.6), 0.1))
checks.expect(
    filter.ingest(grid(centerTorso(2.1), 0.2)).isEmpty,
    "readings that reverse direction are noise, not an approaching object"
)

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(4.5), 0.0))
_ = filter.ingest(grid(centerTorso(2.5), 0.1))
checks.expect(
    filter.ingest(grid(centerTorso(0.5), 0.2)).isEmpty,
    "a 20 m/s approach is a depth artefact, not a thing in the world"
)

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(3.0), 0.0))
_ = filter.ingest(grid(centerTorso(2.8), 0.1))
checks.expectEqual(
    filter.ingest(grid(centerTorso(2.6), 0.2)).count, 1,
    "a plausible, consistent approach is still a real obstacle"
)

checks.section("Closing speed")

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(2.0), 0.0))
_ = filter.ingest(grid(centerTorso(1.9), 0.1))
confirmed = filter.ingest(grid(centerTorso(1.8), 0.2))
checks.expectClose(confirmed.first?.closingSpeed ?? 0, 1.0, 0.01, "closing speed is metres per second")
checks.expectClose(confirmed.first?.timeToContact ?? 0, 1.8, 0.05, "time to contact follows from it")

filter = ObstacleFilter()
_ = filter.ingest(grid(centerTorso(1.80), 0.0))
_ = filter.ingest(grid(centerTorso(1.88), 0.1))
confirmed = filter.ingest(grid(centerTorso(1.94), 0.2))
checks.expect(confirmed.first?.timeToContact == nil, "something receding has no time to contact")

checks.section("Cane and guide-dog users")

var caneSettings = ObstacleFilter.Settings(usesCaneOrGuideDog: true)
var cane = ObstacleFilter(settings: caneSettings)
let ground = [Cell(azimuth: .center, elevation: .ground): 0.8]
_ = cane.ingest(grid(ground, 0.0))
_ = cane.ingest(grid(ground, 0.1))
checks.expect(cane.ingest(grid(ground, 0.2)).isEmpty, "the cane already covers the ground plane")

cane = ObstacleFilter(settings: caneSettings)
let head = [Cell(azimuth: .center, elevation: .head): 0.8]
_ = cane.ingest(grid(head, 0.0))
_ = cane.ingest(grid(head, 0.1))
checks.expectEqual(cane.ingest(grid(head, 0.2)).count, 1, "head height is exactly what a cane misses, so it is never muted")

checks.section("Ordering and convention")

filter = ObstacleFilter()
let scene: [Cell: Double] = [
    Cell(azimuth: .left, elevation: .torso): 3.0,
    Cell(azimuth: .center, elevation: .torso): 1.0,
    Cell(azimuth: .right, elevation: .head): 2.0,
]
_ = filter.ingest(grid(scene, 0.0))
_ = filter.ingest(grid(scene, 0.1))
checks.expectEqual(filter.ingest(grid(scene, 0.2)).map(\.distance), [1.0, 2.0, 3.0], "the nearest obstacle is reported first")
checks.expectEqual(Azimuth.center.clockPosition, 12, "straight ahead is twelve o'clock")
checks.expectEqual(Azimuth.hardLeft.clockPosition, 9, "hard left is nine o'clock")

// MARK: - Announcement priority

checks.section("Announcement priority")

let policy = AnnouncementPolicy()
func say(_ text: String, _ priority: AnnouncementPriority, _ sequence: UInt64) -> Announcement {
    Announcement(text: text, priority: priority, sequence: sequence)
}

let narrating = say("a doorway on your left", .narration, 1)
let danger = say("pole, two meters, ten o'clock", .safety, 2)
checks.expectEqual(
    policy.action(for: danger, speaking: narrating),
    .interrupt(danger),
    "safety cuts into narration"
)
checks.expectEqual(
    policy.action(for: danger, speaking: say("there is a bench", .answer, 3)),
    .interrupt(danger),
    "safety cuts into an answer too"
)
checks.expectEqual(
    policy.action(for: say("a bin ahead", .narration, 4), speaking: say("a chair", .answer, 5)),
    .drop(say("a bin ahead", .narration, 4)),
    "narration never interrupts an answer, and stale narration is dropped rather than queued"
)
checks.expectEqual(
    policy.action(for: say("ready", .system, 6), speaking: nil),
    .speak(say("ready", .system, 6)),
    "with nothing speaking, anything speaks"
)
checks.expectEqual(
    policy.action(for: say("second warning", .safety, 7), speaking: danger),
    .interrupt(say("second warning", .safety, 7)),
    "a newer warning replaces an older one"
)

// MARK: - Motion gate

checks.section("Motion gate")

var gate = MotionGate(verbosity: .sparse)
let origin = MotionGate.Pose(x: 0, z: 0, heading: 0)
checks.expect(gate.shouldSend(pose: origin, now: 0, moving: true), "the first frame always sends")
checks.expect(!gate.shouldSend(pose: origin, now: 1, moving: true), "an unchanged scene sends nothing")

var standing = MotionGate(verbosity: .continuous)
_ = standing.shouldSend(pose: origin, now: 0, moving: false)
var standingSends = 0
for second in 1...60 where standing.shouldSend(pose: origin, now: Double(second), moving: false) {
    standingSends += 1
}
checks.expectEqual(standingSends, 0, "standing still for a minute generates no calls at all")

gate = MotionGate(verbosity: .sparse)
_ = gate.shouldSend(pose: origin, now: 0, moving: true)
checks.expect(
    gate.shouldSend(pose: MotionGate.Pose(x: 0, z: 2.0, heading: 0), now: 0.5, moving: true),
    "walking far enough sends a new frame"
)

gate = MotionGate(verbosity: .sparse)
_ = gate.shouldSend(pose: origin, now: 0, moving: true)
checks.expect(
    gate.shouldSend(pose: MotionGate.Pose(x: 0, z: 0, heading: 0.6), now: 0.5, moving: true),
    "turning the head far enough sends a new frame"
)

gate = MotionGate(verbosity: .sparse)
_ = gate.shouldSend(pose: origin, now: 0, moving: true)
checks.expect(!gate.shouldSend(pose: origin, now: 3, moving: true), "sparse narration waits six seconds")
checks.expect(gate.shouldSend(pose: origin, now: 6.1, moving: true), "and then speaks")

gate = MotionGate(verbosity: .sparse)
_ = gate.shouldSend(pose: origin, now: 0, moving: true)
checks.expect(
    gate.shouldSend(pose: origin, now: 0.1, moving: false, userRequested: true),
    "an explicit tap is never gated"
)

gate = MotionGate(verbosity: .sparse)
_ = gate.shouldSend(pose: MotionGate.Pose(x: 0, z: 0, heading: 0.05), now: 0, moving: true)
checks.expect(
    !gate.shouldSend(pose: MotionGate.Pose(x: 0, z: 0, heading: 6.28), now: 1, moving: true),
    "headings either side of zero are not mistaken for a turn"
)

// MARK: - Sentence chunking

checks.section("Sentence chunking")

var chunker = SentenceChunker()
checks.expectEqual(chunker.feed("Pole,"), ["Pole,"], "a fragment is speakable the moment it is complete")
checks.expectEqual(chunker.feed(" two meters."), ["two meters."], "the next fragment follows")
checks.expect(chunker.flush() == nil, "nothing is left behind")

chunker = SentenceChunker()
checks.expectEqual(chunker.feed("Door"), [], "an incomplete fragment waits")
checks.expectEqual(chunker.feed(" ahead"), [], "and keeps waiting")
checks.expectEqual(chunker.flush() ?? "", "Door ahead", "until the stream ends")

chunker = SentenceChunker(wordLimit: 5)
let long = chunker.feed("one two three four five six seven")
checks.expect(!long.isEmpty, "a long unpunctuated reply still starts speaking")

chunker = SentenceChunker()
var rebuilt = chunker.feed("Stairs").joined()
rebuilt += chunker.feed(" down, three").joined()
rebuilt += chunker.feed(" meters.").joined()
rebuilt += chunker.flush() ?? ""
checks.expect(rebuilt.contains("Stairs"), "no words are lost while streaming")
checks.expect(rebuilt.contains("meters."), "including the last fragment")

checks.report()
