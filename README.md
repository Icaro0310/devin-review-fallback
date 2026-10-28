# devin-review-fallback

Autonomous PR review + merge pipeline that keeps working when your primary AI reviewer doesn't. No paid API keys required.

**The problem:** AI PR reviewers (Devin Review, Copilot code review, CodeRabbit…) are paid or credit-limited. When the trial ends, PRs silently lose their reviewer; the check goes green anyway.

**The fix:** lane A, a free self-hosted LLM review over your own Ollama (reached via Tailscale only), stays on as the deep inspector. Lane B is the devin-judge intercessor: a poordjaevin gate with the ACP backend (high Devin model) run by a laptop-side watcher, whose verdict arrives as the `devin-judge/review` commit status. Deterministic static scanners (gitleaks + semgrep + ruff) remain as advisory evidence. A coverage gate reports what the decider said, and an optional judge-gated auto-merge completes the loop.

```
PR → classify (did the primary reviewer actually RUN?)
     ├ EXECUTED            → coverage: success; fallbacks don't run
     └ anything else       → review-a (Ollama/Tailscale, deep inspector)
                           → static-scan (advisory evidence, on-runner)
                           → judge (waits for devin-judge/review status)
                              → "Review Coverage" check → approve gate
                              → auto-merge (judge-gated)
```

### Lane B: the devin-judge intercessor

Lane B is the devin-judge intercessor: a poordjaevin gate with the ACP backend (high Devin model) run by a laptop-side watcher; the verdict arrives as the `devin-judge/review` commit status on the PR head SHA.

- The watcher (`judge-watch`, cron on the laptop) polls open PRs for head SHAs missing that status, runs the gate locally on the diff, and posts `success` (approve) or `failure` (reject).
- A gate error or an offline watcher posts nothing; the `judge` job reports `UNAVAILABLE` and coverage holds at `action_required`. No status means no verdict, never a green.
- Small models never make security decisions: lane A inspects, the judge decides. A judge reject fails coverage and overrides lane A entirely; lane A alone can never clear a PR.

The workflow's `judge` job tags the PR `judge-requested` (best-effort nudge), polls the commit status every 30s for up to `judge-wait-minutes` (default 15), and comments the verdict. It never checks out the PR; the untrusted diff stays data for the watcher-side gate.

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
| `ai-review-fallback.yml` | classify → review-a (Ollama LLM inspector) + static-scan (advisory) + judge (devin-judge/review verdict) → `Review Coverage` check |
| `auto-merge.yml` | trusted author + approved-on-head + required checks + **poordjaevin judge** (offline NLI, no API key) → `gh pr merge --auto` |

## Quickstart

1. Have an Ollama endpoint reachable over Tailscale for **reviewer A** (tailnet-only; never expose it publicly). The judge and static-scan lanes need no endpoint.
2. Repo **secrets**: `TS_AUTHKEY` (Tailscale auth key tagged `tag:gh-ollama-review`)
3. Repo **variables**: `OLLAMA_TAILNET_URL` (e.g. `http://<your-tailscale-ip>:<port>`), `OLLAMA_MODEL` (e.g. `qwen2.5-coder:3b`)
4. Run the laptop-side watcher (`judge-watch`, on cron every few minutes) with `gh` auth that can post commit statuses; it is what turns PR heads into `devin-judge/review` verdicts. Without it, every fallback PR reports judge `UNAVAILABLE` (action_required, never green).
5. Copy `examples/caller.yml` → `.github/workflows/review-fallback.yml` in your repo.
6. Optional (auto-merge): `gh repo edit <you>/<repo> --enable-auto-merge`.

Pin `@v1` instead of `@main` for supply-chain safety.

## Free alternatives considered

- **Copilot code review**: paid AI credits; Copilot Free plan does not include it.
- **SonarQube Community Build / SonarCloud**: free (self-host / public repos), but SAST, not semantic review. Complement, not substitute.
- **CodeRabbit / Qodo free tiers**: exist, rate-limited; self-hosted Ollama plus the ACP judge is the only unlimited+private path.

## Security boundaries

- `pull_request_target`: the workflow and checked-out bytes come from the base branch; a PR cannot alter its own pipeline.
- No PR code is ever executed: reviewer A reads the diff via the GitHub API; static-scan applies the diff as data onto the trusted base ref and the scanners parse text only; judge checks nothing out at all.
- Small models never make security decisions. The poordjaevin ACP gate (high Devin model) is the final decider: judge reject fails coverage, a missing judge verdict holds coverage at `action_required`, lane A alone cannot clear a PR.
- Ollama is reachable only over Tailscale with an ephemeral tagged node, and only reviewer A uses it.
- `Review Coverage` never spoofs the primary reviewer's context; an absent judge verdict never shows green.
- Everything fails closed: unreachable endpoint, judge error, ambiguous state → no merge.

Community project. Not affiliated with, endorsed by, or sponsored by Cognition AI. "Devin" is a trademark of Cognition AI.

## License

MIT. See [LICENSE](LICENSE).
