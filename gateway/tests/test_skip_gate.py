"""The SKIP gate decides whether a frame is spoken at all."""

from __future__ import annotations

from prompts import SKIP_TOKEN, SkipGate


def drain(deltas):
    gate = SkipGate()
    out = "".join(gate.feed(d) for d in deltas)
    return gate, out


def test_an_exact_skip_reply_speaks_nothing():
    gate, out = drain(["SK", "IP"])
    assert out == ""
    assert gate.is_skip
    assert gate.flush() == ""


def test_a_skip_arriving_as_one_delta_speaks_nothing():
    gate, out = drain([SKIP_TOKEN])
    assert out == ""
    assert gate.is_skip


def test_real_narration_is_released_and_nothing_is_lost():
    deltas = ["Pole", ", two", " meters", ", ten o'clock."]
    gate, out = drain(deltas)
    assert not gate.is_skip
    assert out + gate.flush() == "".join(deltas)


def test_text_that_merely_starts_like_skip_is_still_spoken():
    deltas = ["SK", "ateboard", " ahead"]
    gate, out = drain(deltas)
    assert not gate.is_skip
    assert out + gate.flush() == "SKateboard ahead"


def test_release_happens_early_rather_than_at_the_end():
    # The whole point is streaming: a long reply must not be held to the end.
    gate = SkipGate()
    assert gate.feed("Door") == "Door"
    assert gate.feed(" on your left") == " on your left"


def test_leading_whitespace_does_not_defeat_the_gate():
    gate, out = drain(["  ", "SKIP"])
    assert out == ""
    assert gate.is_skip


def test_flush_returns_held_text_only_once():
    gate = SkipGate()
    gate.feed("S")
    first = gate.flush()
    assert first == "S"
    assert gate.flush() == ""
