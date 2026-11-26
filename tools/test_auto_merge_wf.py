"""Static regression tests for the auto-merge reusable workflow.

Pins the token scopes the merge job's guards need (DL-02c6): on private
repos the check-runs and combined-status reads 403 without checks:read
and statuses:read. With required checks configured every context reads
"not green" and the gate holds every PR (fail-closed, never merges);
without them the universal red-check guard sees an empty list and passes
vacuously — failing CI can be merged over (fail-open). Stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / ".github" / "workflows" / "auto-merge.yml").read_text()
CALLER = (ROOT / "examples" / "caller.yml").read_text()


def _job_block(text: str, name: str) -> str:
    m = re.search(rf"\n  {name}:\n(.*?)(?=\n  \w|\Z)", text, re.S)
    return m.group(1) if m else ""


def test_guards_read_check_runs_and_combined_status():
    """The endpoints the gate calls — keep them pinned so the permission
    block below stays justified, not cargo-culted. Match the actual
    gh(...) call lines: a bare substring also hits the comments that
    justify the permissions, so the test would pass with the call
    removed."""
    calls = "\n".join(l for l in TEXT.splitlines() if "gh(" in l)
    assert re.search(r'commits/\{head_sha\}/check-runs', calls)
    assert re.search(r'commits/\{head_sha\}/status', calls)


def test_merge_job_declares_status_and_check_reads():
    block = _job_block(TEXT, "merge")
    assert "statuses: read" in block
    assert "checks: read" in block
    assert "contents: write" in block       # gh pr merge
    assert "pull-requests: write" in block  # merge + verdict comment


def test_merge_job_grants_no_status_or_check_write():
    """Least privilege: the merge job only reads statuses/check-runs —
    writes to either surface belong to the coverage lane."""
    block = _job_block(TEXT, "merge")
    assert "statuses: write" not in block
    assert "checks: write" not in block


def test_caller_example_grants_status_and_check_reads():
    """Caller permissions cap the reusable workflow's GITHUB_TOKEN — the
    shipped example must grant the merge job the same read scopes or the
    fix above is capped to nothing on private repos."""
    block = _job_block(CALLER, "merge")
    assert "statuses: read" in block
    assert "checks: read" in block
