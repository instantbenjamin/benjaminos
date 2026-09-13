# Portable operational skills

Keep one canonical `skills/<capability>/SKILL.md` per workflow. Deterministic
logic belongs in `packages/<capability>/`, runtime secrets/state outside Git,
and operator instructions in `docs/runbooks/`. Agent identity and personal
knowledge remain in the existing Drive vault.

| Skill | Runtime | Runbook |
|---|---|---|
| [Cinemateca](cinemateca/SKILL.md) | `movie-calendar` CLI; optional stdio MCP | [Movie calendar](../docs/runbooks/movie-calendar.md) |

Agent hosts can load/copy this standard SKILL.md directory into their skill
search path. Codex and Claude Code project discovery links are supplied in
`.agents/skills/` and `.claude/skills/`. Other hosts can call the same CLI or
MCP adapter; they do not need a separate implementation.

ChatGPT web requires a reachable authenticated integration for tool execution.
The included MCP server is local stdio only; publishing a remote adapter and
connecting it to ChatGPT is a separate deployment step. Keep credentials and
the permitted personal account in server configuration, not model arguments.
