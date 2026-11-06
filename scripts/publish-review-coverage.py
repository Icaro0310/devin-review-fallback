#!/usr/bin/env python3
"""Publish the ``Review Coverage`` check run for a PR head SHA.

The failure class this sensor covers:

* A green "Devin Review" status is ambiguous — skipped-for-credits posts
  ``success`` too. Review coverage must be computed from explicit evidence:
  the Devin classification plus the fallback lanes' outcomes.
* The judge is the final decider. Its verdict arrives out-of-band as the
  ``devin-judge/review`` commit status (posted by the laptop-side
  watcher running the poordjaevin ACP gate) and enters here as ``--b``:
  approve is ``EXECUTED``, reject is ``REJECTED``, no status is
  ``UNAVAILABLE``.
* ``ACTION_REQUIRED`` is a first-class verdict: the judge produced no
  verdict at all. Lane A's evidence alone cannot clear a PR — small
  models never make security decisions — so an absent judge means a
  human decides, not a green check.
* The check never impersonates Devin Review: its name is
  ``Review Coverage``, its summary names every evidence source.

Why a check run, not a commit status: a missing judge verdict must not
be green. Commit statuses only know error/failure/pending/success —
publishing judge-absent coverage as ``success`` would repeat the
skipped-as-success bug one layer down. The Checks API has the honest
conclusion: ``action_required`` — a human decides, and the code is not
blamed.

Outputs posted per head SHA:

* check run ``Review Coverage`` — the source of truth the gate reads:
  success | action_required | failure, with the evidence string in
  ``output.summary``.
* commit status ``Review Coverage`` — a compatibility mirror that keeps
  the gate's ``status``-event trigger working (check runs created via
  ``GITHUB_TOKEN`` do not re-dispatch workflows). Mapping:
  success→success, action_required→pending, failure→failure.

Inputs are outcome strings, not job internals:

* ``--devin`` — classifier output: EXECUTED | SKIPPED_CREDITS |
  FAILED_BEFORE_REVIEW | UNVERIFIED (or SKIPPED when the job was skipped).
* ``--a`` — lane A reviewer outcome: EXECUTED | FAILED | UNAVAILABLE
  (or SKIPPED when the job did not run). Advisory evidence only.
* ``--b`` — judge verdict: EXECUTED (approved) | REJECTED | UNAVAILABLE
  (or SKIPPED when the judge job did not run).

Verdicts:

* ``devin=EXECUTED``   → success, coverage by Devin itself.
* ``b=REJECTED``       → failure — the judge rejected the PR. Overrides
                         lane A entirely: the judge is the final
                         decider, so its reject cannot be cleared by
                         advisory evidence.
* ``b=EXECUTED``       → success — the judge approved (lane A is
                         retired, so coverage is judge-only).
* ``b=ERROR``          → ``action_required`` — the judge ran and
                         errored: a human decides, nothing is approved.
* ``b`` anything else  → the check run stays ``in_progress`` and the
                         status mirror stays ``pending``. A verdict not
                         yet arrived is pending, not a failure: the
                         laptop-side watcher completes this check run
                         when ``devin-judge/review`` lands (or marks it
                         ``action_required`` if the gate errored).

Findings are deliberately NOT part of the verdict: a review that ran and
found critical issues is successful execution. The merge gate reads
blocking findings from the check summary and the reviewers' posted
reviews separately.

Usage:
    publish-review-coverage.py --repo owner/name --sha <head_sha>
        --devin S --a S --b S [--dry-run]

``--dry-run`` prints the computed verdict without posting.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

COVERAGE_CONTEXT = "Review Coverage"
EXECUTED = "EXECUTED"
REJECTED = "REJECTED"
ERROR = "ERROR"


def compute_verdict(devin: str, a: str, b: str,
                    a_critical: int = 0) -> tuple[str, str | None, str, str]:
    """Return (check_status, check_conclusion, description, verdict).

    ``check_status`` is ``completed`` or ``in_progress``; the conclusion
    is ``None`` while in progress. ``verdict`` is the coarse label
    embedded in the description.

    ``b`` is the devin-judge verdict — the poordjaevin ACP gate is the
    final decider. ``a`` is informational only (lane A retired 2026-11).
    """
    desc_core = f"devin={devin} a={a} b={b}"
    suffix = f" findings=blocking(critical={a_critical})" if a_critical > 0 else ""
    if devin == EXECUTED:
        return ("completed", "success",
                f"devin=EXECUTED — primary review ran; fallback not needed{suffix}",
                "EXECUTED")
    if b == REJECTED:
        # The judge is the final decider: its reject is terminal.
        return ("completed", "failure",
                f"judge rejected the PR — {desc_core}{suffix}",
                "FAILURE")
    if b == EXECUTED:
        return ("completed", "success",
                f"covered — judge approved — {desc_core}{suffix}",
                "COVERED")
    if b == ERROR:
        # The judge ran and errored: the review cannot conclude — a
        # human decides. Terminal, distinct from "not arrived yet".
        return ("completed", "action_required",
                f"ACTION_REQUIRED — judge errored — {desc_core} — "
                f"a human must decide{suffix}",
                "ACTION_REQUIRED")
    # No judge verdict yet (UNAVAILABLE / SKIPPED / unexpected): pending
    # is not a failure — the watcher completes this run when the
    # verdict lands, or flips it to action_required on gate error.
    return ("in_progress", None,
            f"awaiting devin-judge verdict — {desc_core} — this check "
            f"completes when devin-judge/review lands{suffix}",
            "PENDING")


def _mirror_state(conclusion: str | None) -> str:
    """Check-run conclusion → commit-status state for the mirror."""
    return {"success": "success", "failure": "failure"}.get(
        conclusion or "", "pending")


def _gh(args: list[str]) -> bool:
    env = os.environ.copy()
    if "GH_TOKEN" not in env and env.get("GITHUB_TOKEN"):
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]
    try:
        proc = subprocess.run(["gh", "api", *args], check=False,
                              capture_output=True, text=True, env=env,
                              timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def post_check(repo: str, sha: str, status: str, conclusion: str | None,
               summary: str, details_url: str | None) -> bool:
    """The check run — the source of truth the gate reads.

    ``in_progress`` runs carry no conclusion: they complete later, when
    the watcher-side judge verdict lands.
    """
    cmd = [f"repos/{repo}/check-runs",
           "-f", f"name={COVERAGE_CONTEXT}", "-f", f"head_sha={sha}",
           "-f", f"status={status}",
           "-f", f"output[title]={COVERAGE_CONTEXT}",
           "-f", f"output[summary]={summary}"]
    if conclusion:
        cmd += ["-f", f"conclusion={conclusion}"]
    if details_url:
        cmd += ["-f", f"details_url={details_url}"]
    return _gh(cmd)


def post_status(repo: str, sha: str, conclusion: str | None,
                description: str, target_url: str | None) -> bool:
    """Compatibility mirror: keeps the gate's status-event trigger alive
    for success, and stays ``pending`` while the verdict is in flight."""
    cmd = [f"repos/{repo}/statuses/{sha}",
           "-f", f"state={_mirror_state(conclusion)}",
           "-f", f"context={COVERAGE_CONTEXT}",
           "-f", f"description={description}"]
    if target_url:
        cmd += ["-f", f"target_url={target_url}"]
    return _gh(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--devin", required=True)
    parser.add_argument("--a", default="DISABLED",
                        help="lane A outcome (retired lane — defaults to DISABLED)")
    parser.add_argument("--b", required=True)
    parser.add_argument("--a-critical", type=int, default=0,
                        help="critical findings reported by reviewer A")
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    status, conclusion, description, verdict = compute_verdict(
        args.devin, args.a, args.b, a_critical=args.a_critical)
    print(f"verdict={verdict}")
    print(f"status={status}")
    print(f"conclusion={conclusion}")
    print(f"description={description}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"verdict={verdict}\nconclusion={conclusion or status}\n")
    if args.dry_run:
        return 0
    ok = post_check(args.repo, args.sha, status, conclusion, description,
                    args.target_url)
    if not ok:
        print("::error::failed to post Review Coverage check run",
              file=sys.stderr)
        return 1
    if not post_status(args.repo, args.sha, conclusion, description,
                       args.target_url):
        # the check run (source of truth) is posted; the mirror failing
        # only loses the status-event retrigger — warn instead of
        # hard-failing the job.
        print("::warning::Review Coverage status mirror failed — "
              "check run posted, status-event retrigger lost",
              file=sys.stderr)
    print(f"posted Review Coverage check={status}"
          f"{':' + conclusion if conclusion else ''} on {args.sha[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
