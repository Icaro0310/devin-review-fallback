# devin-review-fallback

Autonomous PR review + merge pipeline that keeps working when your primary AI reviewer doesn't. No paid API keys required.

**The problem:** AI PR reviewers (Devin Review, Copilot code review, CodeRabbit…) are paid or credit-limited. When the trial ends, PRs silently lose their reviewer; the check goes green anyway.

**The fix:** the devin-judge intercessor — a poordjaevin gate with the ACP backend (high Devin model) run by a laptop-side watcher, whose verdict arrives as the `devin-judge/review` commit status. Deterministic static scanners (gitleaks + semgrep + ruff) run on-runner as advisory evidence. A coverage gate reports what the decider said, and an optional judge-gated auto-merge completes the loop.

```
PR → classify (did the primary reviewer actually RUN?)
     ├ EXECUTED            → coverage: success; fallbacks don't run
     └ anything else       → static-scan (advisory evidence, on-runner)
                           → judge (waits for devin-judge/review status)
                              → "Review Coverage" check → approve gate
                              → auto-merge (judge-gated)
```

> Lane A (a free self-hosted LLM review over Tailscale/Ollama) was retired in 2026-11: a 1.5B model is an intern for static data, not a PR reviewer — its advisory output never entered the verdict path, so the lane and its dedicated tailnet door (`tag:gh-ollama-review → tcp:11435`) were removed together.

### The devin-judge intercessor

The decider is a poordjaevin gate with the ACP backend (high Devin model) run by a laptop-side watcher; the verdict arrives as the `devin-judge/review` commit status on the PR head SHA.

- The watcher (`judge-watch`, cron on the laptop) polls open PRs for head SHAs missing that status, posts `pending` (queued) on first sight, runs the gate locally on the diff, and posts `success` (approve) or `failure` (reject). After a verdict it also completes any in-progress `Review Coverage` check run on the SHA — and on repos opted into local coverage it creates the check run itself, with zero Actions minutes.
- **Pending is not a failure:** a verdict still in flight keeps `Review Coverage` `in_progress`/`pending` — never red, never green. A persistent gate error posts `devin-judge/review = error` → `action_required` (a human decides). No status at all means the watcher is down, still pending — still not green.
- Small models never make security decisions: the judge (high Devin model via ACP) is the only decider.

The workflow's `judge` job polls the commit status every 30s for up to `judge-wait-minutes` (default 15) and comments the verdict. It never checks out the PR; the untrusted diff stays data for the watcher-side gate.

### Static scan: advisory evidence

The `static-scan` job keeps the deterministic on-runner scanners as advisory evidence. It checks out the trusted base ref, applies the PR diff as data, and scans the changed files with pinned tools:

| Tool | What it catches |
|---|---|
| gitleaks `8.30.1` (sha256-verified tarball) | secrets/credentials in changed files |
| semgrep `1.182.1` (embedded ruleset, no registry) | eval/exec, `shell=True`, unsafe `yaml.load`, pickle/marshal, SQL string-building, `verify=False`, JS eval/`child_process.exec`, hardcoded secrets |
| ruff `0.17.3` (`--select E9,F,S`, Python diffs only) | syntax errors, pyflakes, flake8-bandit security rules |

One PR comment aggregates per-tool findings (`file:line` only; matched secrets are redacted). Findings are evidence for the judge and humans, not a verdict: `EXECUTED` means the scanners ran, `FAILED` means they didn't. The job always succeeds.

## Workflows (reusable, `workflow_call`)

| Workflow | What it does |
|---|---|
| `ai-review-fallback.yml` | classify → static-scan (advisory) + judge (devin-judge/review verdict) → `Review Coverage` check |
| `auto-merge.yml` | trusted author + approved-on-head + required checks + **poordjaevin judge** (offline NLI, no API key) → `gh pr merge --auto` |

## Quickstart

1. Run the laptop-side watcher (`judge-watch`, on cron) with `gh` auth that can post commit statuses and check runs; it is what turns PR heads into `devin-judge/review` verdicts and completes `Review Coverage`. Without it, coverage stays pending forever — never green.
2. Copy `examples/caller.yml` → `.github/workflows/review-fallback.yml` in your repo.
3. Optional (auto-merge): `gh repo edit <you>/<repo> --enable-auto-merge`.

No repo secrets or variables are needed. Pin `@v1` instead of `@main` for supply-chain safety.

## Free alternatives considered

- **Copilot code review**: paid AI credits; Copilot Free plan does not include it.
- **SonarQube Community Build / SonarCloud**: free (self-host / public repos), but SAST, not semantic review. Complement, not substitute.
- **CodeRabbit / Qodo free tiers**: exist, rate-limited; the ACP judge plus local coverage is the only unlimited+private path.
- **Self-hosted Ollama review (retired here)**: a small local model is an intern for static data, not a PR decider — it cost runner minutes and tailnet surface without ever entering the verdict path.

## Security boundaries

- `pull_request_target`: the workflow and checked-out bytes come from the base branch; a PR cannot alter its own pipeline.
- No PR code is ever executed: static-scan applies the diff as data onto the trusted base ref and the scanners parse text only; judge checks nothing out at all.
- Small models never make security decisions. The poordjaevin ACP gate (high Devin model) is the final decider: judge reject fails coverage, judge error posts `action_required`, a missing verdict stays pending.
- `Review Coverage` never spoofs the primary reviewer's context; an absent judge verdict never shows green.
- Everything fails closed: judge error, ambiguous state, offline watcher → pending or human decision, never an approval.
- If the ACP backend itself becomes unavailable (free-tier drift), nothing is auto-approved: deterministic scans still run, verdicts stay absent, review falls back to humans. A daily canary on the laptop probes the gate and alerts on failure.

Community project. Not affiliated with, endorsed by, or sponsored by Cognition AI. "Devin" is a trademark of Cognition AI.

## License

MIT. See [LICENSE](LICENSE).
