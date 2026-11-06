"""Tests for scripts/publish-review-coverage.py — verdict matrix.

Contract under test: ``--b`` is the devin-judge verdict (the poordjaevin
ACP gate is the final decider). EXECUTED means approved, REJECTED means
rejected, ERROR means the gate ran and failed, and anything else means
the verdict is still in flight — pending is not a failure, so the check
run stays ``in_progress`` until the watcher completes it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_review_coverage",
    ROOT / "scripts" / "publish-review-coverage.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_devin_executed_needs_no_fallback():
    status, conclusion, desc, verdict = mod.compute_verdict(
        "EXECUTED", "DISABLED", "SKIPPED")
    assert status == "completed" and conclusion == "success"
    assert verdict == "EXECUTED"
    assert "fallback not needed" in desc


def test_judge_approve_is_covered():
    status, conclusion, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "DISABLED", "EXECUTED")
    assert status == "completed" and conclusion == "success"
    assert verdict == "COVERED"
    assert "judge approved" in desc
    assert "devin=SKIPPED_CREDITS" in desc


def test_judge_approve_with_lane_a_result_still_covered():
    """A retired lane A value in the description never changes the
    verdict — the judge alone decides."""
    status, conclusion, desc, verdict = mod.compute_verdict(
        "UNVERIFIED", "EXECUTED", "EXECUTED")
    assert status == "completed" and conclusion == "success"
    assert verdict == "COVERED"


def test_judge_reject_is_failure():
    status, conclusion, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "EXECUTED", "REJECTED")
    assert status == "completed" and conclusion == "failure"
    assert verdict == "FAILURE"
    assert "judge rejected" in desc


def test_judge_error_is_action_required_not_pending():
    """The gate ran and errored: terminal, a human decides — distinct
    from a verdict still in flight."""
    status, conclusion, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "DISABLED", "ERROR")
    assert status == "completed" and conclusion == "action_required"
    assert verdict == "ACTION_REQUIRED"
    assert "judge errored" in desc


def test_missing_verdict_is_pending_not_failure():
    """b=UNAVAILABLE: the watcher may still be working — pending is not
    a failure, the check run stays open until the verdict lands."""
    status, conclusion, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "DISABLED", "UNAVAILABLE")
    assert status == "in_progress" and conclusion is None
    assert verdict == "PENDING"
    assert "awaiting devin-judge verdict" in desc


def test_skipped_judge_is_pending():
    status, conclusion, _, verdict = mod.compute_verdict(
        "FAILED_BEFORE_REVIEW", "DISABLED", "SKIPPED")
    assert status == "in_progress" and conclusion is None
    assert verdict == "PENDING"


def test_unexpected_judge_value_is_pending():
    """Unknown states degrade to pending, never to a terminal guess."""
    status, conclusion, _, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "DISABLED", "FAILED")
    assert status == "in_progress" and conclusion is None
    assert verdict == "PENDING"


def test_unverified_devin_still_judged():
    _, _, _, verdict = mod.compute_verdict("UNVERIFIED", "DISABLED", "EXECUTED")
    assert verdict == "COVERED"


def test_failed_before_review_uses_fallback():
    _, _, _, verdict = mod.compute_verdict(
        "FAILED_BEFORE_REVIEW", "DISABLED", "EXECUTED")
    assert verdict == "COVERED"


def test_critical_findings_marker_on_covered():
    _, _, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "EXECUTED", "EXECUTED", a_critical=2)
    assert verdict == "COVERED"
    assert "findings=blocking(critical=2)" in desc


def test_critical_findings_marker_on_rejected():
    _, _, desc, verdict = mod.compute_verdict(
        "SKIPPED_CREDITS", "EXECUTED", "REJECTED", a_critical=1)
    assert verdict == "FAILURE"
    assert "findings=blocking" in desc


def test_mirror_state_never_greens_without_verdict():
    """The compatibility status mirror: pending/in-flight and
    action_required both mirror to pending — never green without a
    judge verdict."""
    assert mod._mirror_state("success") == "success"
    assert mod._mirror_state("failure") == "failure"
    assert mod._mirror_state("action_required") == "pending"
    assert mod._mirror_state(None) == "pending"
