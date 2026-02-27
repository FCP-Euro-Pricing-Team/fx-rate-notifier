# Design: `/review-and-fix` Skill

**Date:** 2026-02-27
**Status:** Approved
**Author:** Claude + Damie Adams

## Problem

CodeRabbit reviews PRs but cannot create consolidated issues or assign Copilot via MCP tools (MCP integration is read-only context enrichment). The Copilot automation chain is broken and unreliable.

## Solution

A Claude Code skill (`/review-and-fix`) that handles the full review-and-fix loop locally. No GitHub Actions, no Copilot, no MCP tools needed.

## Workflow

```
/commit-push-pr → CodeRabbit reviews → /review-and-fix kicks in automatically
```

### Skill Steps

1. **Wait for CodeRabbit** — poll PR for CHANGES_REQUESTED (skip if already present)
2. **Read CodeRabbit findings** — extract review comments via `gh api`
3. **Run Claude review** — invoke pr-review-toolkit agents
4. **Create consolidated GitHub issue** — all findings in one issue with labels
5. **Fix everything** — apply fixes on same branch
6. **Push fixes** — commit and push to existing PR
7. **Wait for re-review** — poll for approval or another round
8. **Loop if needed** — max 3 rounds
9. **Report** — "Ready for your approval" or "needs your input"

### Invocation

- `/review-and-fix` — auto-detects current branch's open PR
- `/review-and-fix 11` — explicit PR number
- `/review-and-fix owner/repo#11` — cross-repo

### CLAUDE.md Auto-Chaining

After any PR push to FCP-Euro-Pricing-Team repos, Claude automatically:
1. Polls for CodeRabbit review (every 60s, up to 10 min)
2. If CHANGES_REQUESTED → invokes `/review-and-fix`
3. If APPROVED → notifies user

### Guardrails

- Max 3 fix rounds (prevents infinite loops)
- Same branch, same PR (no PR sprawl)
- Issue linked with `Fixes #issue` in commit
- Never merges — stops at "ready for approval"

### What Gets Removed

- `coderabbit-copilot-automation.yml` from fx-rate-notifier and weather-revenue-tracker
- Copilot seat dependency in CodeRabbit UI
- MCP server instructions for Copilot in CodeRabbit UI (optional to remove)
