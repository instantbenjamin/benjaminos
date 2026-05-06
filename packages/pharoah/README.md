# packages/pharoah

The Pharoah agent's behavior code — what runs when Pharoah does something.

Pharoah's *identity* lives at `Shared drives/BenjaminOS/5-System/agent/SKILL.md` (canonical) and `packages/hermes/SOUL.md` (compressed for the Hermes runtime). This package is for the *behavior* — classifiers, renderers, twin-mind interfaces, etc.

## Planned modules

- `classifier.py` *(BEN-51)* — Routes captures to right store: task → Linear, idea → wiki, habit → Supabase, signal → GBrain
- `daily_brief.py` *(BEN-19)* — 7-panel morning artifact renderer
- `twin_mind.py` *(future)* — Surfaces Benjamin's prior decisions / opinions / journal context on demand
- `decision_matrix.py` *(future)* — Help Benjamin decide what matters today (priority/effort/leverage scoring)

## Conventions

- Pure functions where possible; side effects (DB writes, Linear API calls, etc.) isolated to thin adapter layers
- Stateless modules; state lives in Supabase / GBrain / Linear
- Classifier produces *intents*, not *actions*. Adapter layer turns intents into API calls.
