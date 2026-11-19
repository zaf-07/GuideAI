"""The banned-phrase test (spec section 16).

Absence of detection is not detection of absence. A blind user who hears
"path is clear" and steps forward is the single failure this app exists to
prevent, so no shipped user-facing string may assert safety -- including the
prompts that instruct the model.

This test is meant to fail the build. If a new string trips it, change the
string; do not add it to an allow list.

Scope is string *literals*, reached through the AST rather than by scanning
lines, so that `dict.clear()` and a method named `clear` are not mistaken for
a claim about the world. Docstrings are excluded: they explain the rule to
the next engineer and are never spoken to a user.
"""

from __future__ import annotations

import ast
import pathlib
import re

import prompts

BANNED = [
    r"\bclear\b",
    r"\bsafe to\b",
    r"\bnothing ahead\b",
    r"\bno obstacles\b",
    r"\ball clear\b",
]

# The prompts must name these phrases in order to forbid them. A negated
# mention is the opposite of an assertion.
NEGATION = re.compile(r"\bnever\b", re.IGNORECASE)

GATEWAY = pathlib.Path(__file__).resolve().parent.parent


def offending(text: str) -> list[str]:
    """Lines of `text` that assert safety rather than forbidding it."""
    hits = []
    for line in text.splitlines():
        if NEGATION.search(line):
            continue
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in BANNED):
            hits.append(line.strip())
    return hits


def _docstrings(tree: ast.AST) -> set[int]:
    """Ids of string nodes that are docstrings, which are never user-facing."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    found.add(id(body[0].value))
    return found


def string_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    skip = _docstrings(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


def test_narration_prompt_forbids_asserting_safety():
    assert "Never say the path is clear" in prompts.NARRATION_SYSTEM_PROMPT
    assert not offending(prompts.NARRATION_SYSTEM_PROMPT)


def test_dialogue_prompt_forbids_asserting_safety():
    assert "Never say the path is clear" in prompts.DIALOGUE_SYSTEM_PROMPT
    assert not offending(prompts.DIALOGUE_SYSTEM_PROMPT)


def test_no_shipped_string_asserts_safety():
    offenders: dict[str, list[str]] = {}
    for path in sorted(GATEWAY.glob("*.py")):
        for literal in string_literals(path.read_text()):
            hits = offending(literal)
            if hits:
                offenders.setdefault(path.name, []).extend(hits)
    assert not offenders, f"Strings asserting safety must not ship: {offenders}"


def test_the_test_actually_catches_a_banned_phrase():
    # A safety test that cannot fail is not a safety test.
    assert offending("The path ahead is clear.")
    assert offending("It is safe to proceed.")
    assert offending("Nothing ahead of you.")
    assert offending("There are no obstacles.")
    assert offending("All clear!")
    assert not offending("Pole, two meters, ten o'clock.")
    assert not offending("Never say the path is clear.")


def test_identifiers_are_not_mistaken_for_claims():
    # `dict.clear()` is not a statement about the world.
    assert not offending_source("def clear(self): self._spend.clear()")


def offending_source(source: str) -> list[str]:
    hits: list[str] = []
    for literal in string_literals(source):
        hits.extend(offending(literal))
    return hits
