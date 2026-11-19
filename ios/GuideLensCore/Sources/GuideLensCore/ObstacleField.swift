import Foundation

/// Where a cell sits horizontally, as the user would describe it.
public enum Azimuth: Int, Sendable, CaseIterable {
    case hardLeft = 0, left, center, right, hardRight

    /// Clock position, which is how orientation-and-mobility training frames
    /// direction and therefore how the app speaks it.
    public var clockPosition: Int {
        switch self {
        case .hardLeft: return 9
        case .left: return 10
        case .center: return 12
        case .right: return 2
        case .hardRight: return 3
        }
    }
}

/// Height band. Head height matters most: it is exactly what a cane misses.
public enum Elevation: Int, Sendable, CaseIterable {
    case ground = 0, torso, head
}

public struct Cell: Sendable, Hashable {
    public let azimuth: Azimuth
    public let elevation: Elevation
    public init(azimuth: Azimuth, elevation: Elevation) {
        self.azimuth = azimuth
        self.elevation = elevation
    }
}

public struct Obstacle: Sendable, Equatable {
    public let cell: Cell
    /// Metres, from the 10th percentile of the cell's valid depths.
    public let distance: Double
    /// Positive means closing. Metres per second.
    public let closingSpeed: Double
    /// Seconds until contact at the current closing speed, if it is closing.
    public let timeToContact: Double?
}

/// One frame of depth, already downsampled to the 5x3 grid.
public struct DepthGrid: Sendable {
    public static let columns = Azimuth.allCases.count
    public static let rows = Elevation.allCases.count

    /// Metres per cell. `nil` where every sample was rejected for low
    /// confidence — which is not the same as "nothing there", and must never
    /// be reported as clearance.
    public private(set) var cells: [Cell: Double]
    public let timestamp: Double

    public init(cells: [Cell: Double], timestamp: Double) {
        self.cells = cells
        self.timestamp = timestamp
    }

    public func distance(_ azimuth: Azimuth, _ elevation: Elevation) -> Double? {
        cells[Cell(azimuth: azimuth, elevation: elevation)]
    }
}

/// Reduces a cell's depth samples to one number.
///
/// The 10th percentile, never the minimum: a single rogue pixel is noise,
/// while a tenth of the cell agreeing is an object. Using the minimum here
/// is the classic way to produce phantom obstacles.
public func tenthPercentile(_ samples: [Double]) -> Double? {
    let valid = samples.filter { $0.isFinite && $0 > 0 }.sorted()
    guard !valid.isEmpty else { return nil }
    let index = Int((Double(valid.count - 1) * 0.10).rounded())
    return valid[index]
}

/// Turns a stream of depth grids into obstacles worth acting on.
///
/// The temporal filter is the single most valuable rule in the app: a cell
/// becomes active only once three consecutive frames agree within 15cm.
/// One phantom obstacle that stops a blind user mid-stride costs more trust
/// than a dozen missed chairs, because the user stops believing the app.
public struct ObstacleFilter: Sendable {
    public struct Settings: Sendable {
        /// Frames that must agree before a cell is believed.
        public var agreementFrames: Int
        /// How closely those frames must agree, in metres.
        public var agreementTolerance: Double
        /// Nothing beyond this is worth saying anything about.
        public var maxRange: Double
        /// Cane and guide-dog users get later, sparser alerts: the cane
        /// already covers the ground plane, and repeating it is noise.
        public var usesCaneOrGuideDog: Bool
        /// Ground-row alerts are suppressed closer than this for cane users.
        public var caneGroundSuppressionRange: Double
        /// Fastest approach treated as a real object rather than bad depth.
        /// A running person closes at roughly 4 m/s; anything quicker than
        /// this across one frame is a depth artefact, not a thing.
        public var maxClosingSpeed: Double

        public init(
            agreementFrames: Int = 3,
            agreementTolerance: Double = 0.15,
            maxRange: Double = 5.0,
            usesCaneOrGuideDog: Bool = false,
            caneGroundSuppressionRange: Double = 1.0,
            maxClosingSpeed: Double = 4.0
        ) {
            self.agreementFrames = agreementFrames
            self.agreementTolerance = agreementTolerance
            self.maxRange = maxRange
            self.usesCaneOrGuideDog = usesCaneOrGuideDog
            self.caneGroundSuppressionRange = caneGroundSuppressionRange
            self.maxClosingSpeed = maxClosingSpeed
        }
    }

    public let settings: Settings
    private var history: [DepthGrid]

    public init(settings: Settings = Settings()) {
        self.settings = settings
        self.history = []
    }

    /// Feed one frame; get back the obstacles currently worth signalling.
    public mutating func ingest(_ grid: DepthGrid) -> [Obstacle] {
        history.append(grid)
        if history.count > 8 { history.removeFirst(history.count - 8) }
        guard history.count >= settings.agreementFrames else { return [] }

        let recent = Array(history.suffix(settings.agreementFrames))
        var obstacles: [Obstacle] = []

        for azimuth in Azimuth.allCases {
            for elevation in Elevation.allCases {
                let cell = Cell(azimuth: azimuth, elevation: elevation)
                let readings = recent.compactMap { $0.cells[cell] }
                // A cell missing from any recent frame has not been confirmed.
                guard readings.count == settings.agreementFrames else { continue }
                guard let newest = readings.last, newest <= settings.maxRange else { continue }
                guard agrees(readings, frames: recent) else { continue }

                if settings.usesCaneOrGuideDog,
                   elevation == .ground,
                   newest < settings.caneGroundSuppressionRange {
                    continue
                }

                let speed = closingSpeed(readings: readings, frames: recent)
                let ttc = speed > 0.05 ? newest / speed : nil
                obstacles.append(
                    Obstacle(cell: cell, distance: newest, closingSpeed: speed, timeToContact: ttc)
                )
            }
        }
        return obstacles.sorted { $0.distance < $1.distance }
    }

    /// Do these readings describe one thing, or bad depth?
    ///
    /// Two ways to qualify. A still object holds within the tolerance. A
    /// moving one will not: something closing at 1 m/s covers 0.2m across
    /// three frames at 10Hz, well past a 15cm window, and treating that as
    /// noise would discard exactly the obstacles that matter most. So a
    /// consistent direction of travel also qualifies, provided each step is
    /// physically plausible. What stays rejected is what noise actually
    /// looks like: readings jumping back and forth, or leaping implausibly
    /// far between frames.
    private func agrees(_ readings: [Double], frames: [DepthGrid]) -> Bool {
        guard let low = readings.min(), let high = readings.max() else { return false }
        if high - low <= settings.agreementTolerance { return true }

        var deltas: [Double] = []
        for index in 1..<readings.count {
            let elapsed = frames[index].timestamp - frames[index - 1].timestamp
            guard elapsed > 0 else { return false }
            let step = readings[index] - readings[index - 1]
            if abs(step) / elapsed > settings.maxClosingSpeed { return false }
            deltas.append(step)
        }
        guard let first = deltas.first else { return false }
        // Every step must run the same way; a reading that reverses is noise.
        return deltas.allSatisfy { ($0 > 0) == (first > 0) && $0 != 0 }
    }

    /// Positive when the gap is shrinking. Derived from the filtered
    /// distances rather than raw depth, so noise does not read as motion.
    private func closingSpeed(readings: [Double], frames: [DepthGrid]) -> Double {
        guard readings.count >= 2, frames.count >= 2 else { return 0 }
        let elapsed = frames[frames.count - 1].timestamp - frames[0].timestamp
        guard elapsed > 0 else { return 0 }
        return (readings[0] - readings[readings.count - 1]) / elapsed
    }

    public mutating func reset() { history.removeAll() }
}
