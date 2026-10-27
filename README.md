# devin-review-fallback

Autonomous PR review + merge pipeline that keeps working when your primary AI reviewer doesn't — no paid API keys required.

**The problem:** AI PR reviewers (Devin Review, Copilot code review, CodeRabbit…) are paid or credit-limited. When the trial ends, PRs silently lose their reviewer — the check goes green anyway.

**The fix:** two free, self-hosted reviewers over your own Ollama (reached via Tailscale only), a coverage gate that reports honest review evidence, and an optional judge-gated auto-merge.

```
PR → classify (did the primary reviewer actually RUN?)
     ├ EXECUTED            → coverage: success — fallbacks don't run
     └ anything else       → review-a + review-b (Ollama/Tailscale)
                              → "Review Coverage" check → approve gate
                              → auto-merge (judge-gated)
```

## Workflows (reusable, `workflow_call`)

| Workflow | What it does |
|---|---|
| `ai-review-fallback.yml` | classify → 2 Ollama reviewers (API-diff only, no PR code execution) → `Review Coverage` check |
| `auto-merge.yml` | trusted author + approved-on-head + required checks + **poordjaevin judge** (offline NLI, no API key) → `gh pr merge --auto` |

## Quickstart

1. Have an Ollama endpoint reachable over Tailscale (tailnet-only — never expose it publicly).
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
- No PR code is ever executed (reviewers read the diff via the GitHub API / base-ref checkout with tool-mode off).
- Ollama is reachable only over Tailscale with an ephemeral tagged node.
- `Review Coverage` never spoofs the primary reviewer's context; DEGRADED coverage never shows green.
- Everything fails closed: unreachable endpoint, judge error, ambiguous state → no merge.

Community project. Not affiliated with, endorsed by, or sponsored by Cognition AI. "Devin" is a trademark of Cognition AI.

## License

MIT — see [LICENSE](LICENSE).
