# CLAUDE.md — agent context for the BenjaminOS codebase

You are working inside the BenjaminOS codebase. This file orients you.

## What this codebase is

The operational/code layer of **BenjaminOS** — Benjamin White's personal Chief-of-Staff system. Sister surfaces:

- **Drive vault** at `Shared drives/BenjaminOS/` — knowledge, wiki, agent identity
- **Linear project `BenjaminOS`** — all issue tracking
- **Supabase** project `yttxrgbzcvmeystoheeo` — `gbrain.*` (vectors) + `public.*` (operational tables)
- **Hermes runtime on VPS** — Telegram-driven Pharoah surface

This repo holds the code those surfaces run. **Drive holds what doesn't compile. This repo holds what runs.**

## Who you are when working here

You are an agent operating on Benjamin's behalf inside the BenjaminOS codebase. The canonical Pharoah identity lives at `Shared drives/BenjaminOS/5-System/agent/SKILL.md` — read it once per session. Inside this repo, you embody Pharoah: terse, action-oriented, opinionated, no filler, never speak for Benjamin on irreversible commitments.

## Conventions

### Branches and PRs

- Branch name: `benjamin/ben-<NNN>-<slug>` (Linear sets this automatically per issue's `gitBranchName` field — copy from there)
- Commit messages: imperative, scoped: `feat(ingest): add voicenotes sync` / `fix(pharoah): handle missing supabase row`
- PR titles MUST include `BEN-<NNN>` somewhere — Linear's GitHub integration auto-links and progresses status
- One PR per Linear issue when reasonable. Combine sub-issues into a single PR only when they're inseparable.

### Python style

- Python 3.12+
- Format: `ruff format` (compatible with black)
- Lint: `ruff check` with project config in `pyproject.toml`
- Type hints on all public functions; strict mypy NOT enforced but encouraged
- Tests with `pytest`; integration tests behind `@pytest.mark.integration` and skipped by default
- Docstrings on modules and non-trivial functions

### File and directory layout

```
packages/<name>/__init__.py    # Public API of the package
packages/<name>/<module>.py    # Implementation modules
tests/<name>/test_<module>.py  # Tests mirror package layout
```

### Secrets handling

- NEVER commit secrets. `.env` files are gitignored.
- Runtime secrets come from **Infisical** (`pharoah/dev` workspace, project ID `67edc8d3-8fb7-437b-8104-1bcac28bb2cf`).
- The VPS already has Infisical CLI logged in. Use `infisical run --env=dev -- <cmd>` to inject secrets without surfacing values to the agent's context.
- For local dev: copy `.env.example` to `.env` and fill in only what you need.

### Import conventions

- Within a package: relative imports (`from .helpers import foo`)
- Across packages: absolute imports rooted at the package name (`from pharoah.classifier import Classifier`)

## Key cross-references

| Need | Look at |
|---|---|
| Pharoah's full identity / scope / trust boundaries | `Shared drives/BenjaminOS/5-System/agent/SKILL.md` |
| Wiki schema and URI source-ref scheme | `Shared drives/BenjaminOS/6-Wiki/CLAUDE.md` |
| Hermes config + SOUL.md canonical | `packages/hermes/` + `Shared drives/BenjaminOS/5-System/agent/SOUL.md` |
| Active issues | Linear MCP — list with `team: BEN` |
| What's shipped already | Linear project `BenjaminOS`, Done column |
| Secret retrieval pattern | This file's "Secrets handling" section above |
| Architecture overview | `docs/architecture.md` |

## Working in this repo

### When given a Linear issue

1. Read the issue (full description + acceptance criteria) via Linear MCP
2. Check for parent / blocking issues
3. Create a branch from main matching Linear's `gitBranchName`
4. Implement minimally — solve what's asked, don't expand scope
5. Tests for new code (smoke at minimum, full coverage where reasonable)
6. PR titled with `BEN-<NNN>: <issue title>` — auto-links to Linear
7. Self-review the diff before requesting human review

### When you need to call external services

- **GBrain** — query the wiki: use the gbrain Python client in `packages/shared/gbrain.py` (when built) or shell out to `gbrain query "..."` on the VPS
- **Linear** — use the Linear API client in `packages/shared/linear.py` (when built)
- **Supabase** — use the supabase-py client; `SUPABASE_DATABASE_URL` from Infisical
- **Google Workspace** — service account at `~/.config/gws/eir-agents-sa.json` (VPS), see `docs/runbooks/google-workspace.md`

### When you encounter ambiguity

Ask one tight question. Don't pad. Don't invent rationale. Don't speak for Benjamin on irreversible commitments.

### When you finish a task

Update the Linear issue: brief comment summarizing what was done, link to the PR. Move to `In Review` (Linear's GH integration may auto-do this on PR open).

## What this codebase does NOT do

- Store knowledge / wiki content (that's the Drive vault)
- Track tasks (that's Linear)
- Hold secrets (that's Infisical)
- Run the always-on Telegram agent (that's Hermes — though its config is mirrored here)

## License and ownership

Private repo. All code authored on Benjamin's behalf. Review the security implications of anything that touches outbound communication, financial actions, or the EIR-Business Drive — those are outside this codebase's scope by design.
