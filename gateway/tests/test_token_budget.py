"""The hourly ceiling that rate limits alone cannot provide."""

from __future__ import annotations

from token_budget import WINDOW_SECONDS, TokenBudget

DEVICE = "device-aaa"


def test_a_fresh_device_is_allowed():
    assert TokenBudget(1000).allows(DEVICE)


def test_spending_accumulates():
    budget = TokenBudget(1000)
    budget.record(DEVICE, 400, now=0)
    budget.record(DEVICE, 300, now=10)
    assert budget.spent(DEVICE, now=20) == 700
    assert budget.allows(DEVICE, now=20)


def test_the_ceiling_stops_a_looping_client():
    budget = TokenBudget(1000)
    budget.record(DEVICE, 1000, now=0)
    assert not budget.allows(DEVICE, now=1)


def test_the_window_rolls_forward():
    budget = TokenBudget(1000)
    budget.record(DEVICE, 1000, now=0)
    assert not budget.allows(DEVICE, now=WINDOW_SECONDS - 1)
    assert budget.allows(DEVICE, now=WINDOW_SECONDS + 1)


def test_devices_have_separate_budgets():
    budget = TokenBudget(1000)
    budget.record(DEVICE, 1000, now=0)
    assert not budget.allows(DEVICE, now=1)
    assert budget.allows("device-bbb", now=1)


def test_zero_and_negative_spends_are_ignored():
    budget = TokenBudget(1000)
    budget.record(DEVICE, 0, now=0)
    budget.record(DEVICE, -5, now=0)
    assert budget.spent(DEVICE, now=0) == 0
