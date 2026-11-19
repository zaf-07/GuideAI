import Foundation

/// A minimal assertion harness.
///
/// XCTest and swift-testing both ship with Xcode, which this machine cannot
/// install, so the checks run as an ordinary executable. Exit status is the
/// contract: zero means every rule held.
struct Checks {
    private(set) var failures: [String] = []
    private(set) var passed = 0
    private var group = ""

    mutating func section(_ name: String) {
        group = name
        print("\n\(name)")
    }

    mutating func expect(_ condition: Bool, _ what: String) {
        if condition {
            passed += 1
            print("  ok   \(what)")
        } else {
            failures.append("\(group): \(what)")
            print("  FAIL \(what)")
        }
    }

    mutating func expectEqual<T: Equatable>(_ actual: T, _ expected: T, _ what: String) {
        expect(actual == expected, "\(what) (got \(actual), expected \(expected))")
    }

    mutating func expectClose(_ actual: Double, _ expected: Double, _ tolerance: Double, _ what: String) {
        expect(abs(actual - expected) <= tolerance, "\(what) (got \(actual), expected ~\(expected))")
    }

    func report() -> Never {
        print("\n\(passed) passed, \(failures.count) failed")
        for failure in failures { print("  FAILED: \(failure)") }
        exit(failures.isEmpty ? 0 : 1)
    }
}
