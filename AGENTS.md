# Agent instructions — nethealth

nethealth — network diagnostic TUI (traceroute, packet sniffer, gateway/IP checks). Feature-complete, maintenance in scope.

- **Stack:** Python, Click, Rich, Textual
- **Vault note:** `ProjectVault/01_Repositories/nethealth.md` — read it for current status, history, and open loops before non-trivial work. It is canonical over anything stale here.
- **Runtime preflight:** python + pip; pytest (125 tests)
- **Deploy:** none — local CLI/TUI

## Operating contract (Claude Code + Codex)

Austin's global rules live in `~/.claude/CLAUDE.md` + `CLAUDE-shared.md` (Claude Code) and
`~/.codex/AGENTS.md` (Codex) — same contract, both agents. Load-bearing: simplest viable
solution first (no new scripts/infra unless asked), confirm the path before editing, todos are
per-project (never a global TASKS.md), the git workflow in that contract (small solo repos: commit straight to the default branch; session end syncs every touched repo — commit, push, merge/prune — without asking), session-end `/document` capture to the vault if the work produced a decision/fix/learning.
