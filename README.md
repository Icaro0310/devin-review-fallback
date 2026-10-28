# devin-review-fallback

Autonomous PR review + merge pipeline that keeps working when your primary AI reviewer doesn't — no paid API keys required.

**The problem:** AI PR reviewers (Devin Review, Copilot code review, CodeRabbit…) are paid or credit-limited. When the trial ends, PRs silently lose their reviewer — the check goes green anyway.

**The fix:** two independent fallback lanes — reviewer A, a free self-hosted LLM review over your own Ollama (reached via Tailscale only), and reviewer B, a deterministic static-analysis lane (gitleaks + semgrep + ruff) that runs entirely on the GitHub runner — a coverage gate that reports honest review evidence, and an optional judge-gated auto-merge.

```
PR → classify (did the primary reviewer actually RUN?)
     ├ EXECUTED            → coverage: success — fallbacks don't run
     └ anything else       → review-a (Ollama/Tailscale)
                           → review-b (static analysis, on-runner)
                              → "Review Coverage" check → approve gate
                              → auto-merge (judge-gated)
```

### Lane B: deterministic, zero-VM

Reviewer B needs **no model, no VM, no secrets**. It checks out the trusted base ref, applies the PR diff as data, and scans the changed files with pinned tools:

| Tool | What it catches |
|---|---|
| gitleaks `8.30.1` (sha256-verified tarball) | secrets/credentials in changed files |
| semgrep `1.182.1` (embedded ruleset, no registry) | eval/exec, `shell=True`, unsafe `yaml.load`, pickle/marshal, SQL string-building, `verify=False`, JS eval/`child_process.exec`, hardcoded secrets |
| ruff `0.17.3` (`--select E9,F,S`, Python diffs only) | syntax errors, pyflakes, flake8-bandit security rules |

One PR comment aggregates per-tool findings (`file:line` only — matched secrets are redacted). Findings are evidence, not lane failures: `EXECUTED` means the scanners ran.

## Workflows (reusable, `workflow_call`)

| Workflow | What it does |
|---|---|
| `ai-review-fallback.yml` | classify → review-a (Ollama LLM) + review-b (static analysis) → `Review Coverage` check |
| `auto-merge.yml` | trusted author + approved-on-head + required checks + **poordjaevin judge** (offline NLI, no API key) → `gh pr merge --auto` |

## Quickstart

1. Have an Ollama endpoint reachable over Tailscale for **reviewer A** (tailnet-only — never expose it publicly). Reviewer B needs nothing — it is deterministic static analysis on the runner.
2. Repo **secrets**: `TS_AUTHKEY` (Tailscale auth key tagged `tag:gh-ollama-review`)
3. Repo **variables**: `OLLAMA_TAILNET_URL` (e.g. `http://<your-tailscale-ip>:<port>`), `OLLAMA_MODEL` (e.g. `qwen2.5-coder:3b`)
4. Copy `examples/caller.yml` → `.github/workflows/review-fallback.yml` in your repo.
5. Optional (auto-merge): `gh repo edit <you>/<repo> --enable-auto-merge`.

Pin `@v1` instead of `@main` for supply-chain safety.

## Free alternatives considered

- **Copilot code review** — paid AI credits; Copilot Free plan does not include it.
- **SonarQube Community Build / SonarCloud** — free (self-host / public repos), but SAST, not semantic review. Complement, not substitute.
- **CodeRabbit / Qodo free tiers** — exist, rate-limited; self-hosted Ollama is the only unlimited+private path.

## Security boundaries

- `pull_request_target`: the workflow and checked-out bytes come from the base branch — a PR cannot alter its own pipeline.
- No PR code is ever executed: reviewer A reads the diff via the GitHub API; reviewer B applies the diff as data onto the trusted base ref and the scanners parse text only.
- Ollama is reachable only over Tailscale with an ephemeral tagged node, and only reviewer A uses it.
- `Review Coverage` never spoofs the primary reviewer's context; DEGRADED coverage never shows green.
- Everything fails closed: unreachable endpoint, judge error, ambiguous state → no merge.

Community project. Not affiliated with, endorsed by, or sponsored by Cognition AI. "Devin" is a trademark of Cognition AI.

## License

MIT — see [LICENSE](LICENSE).
