# Learned memory

The agent's own compiled memory of verified **pitfalls** (error → fix lessons) and
reusable **recipes** (verified scripts), maintained by `src/imagentj/tools/learned_memory.py`.

This **data** store is writable (so it lives in `/app/data/learned`, not the
read-only `/app/skills` tree). The Librarian subagent's *operating manual* is a
separate, real loaded skill at `skills/learned_memory/SKILL.md`. The agents reach
this store at runtime through:
- **auto-injection** — `core_pitfalls()` and `core_recipes()` put the CORE sets into
  every coder/debugger/analyst prompt (the can't-miss floor);
- the **`recall` tool** — the coder/debugger/analyst pull task/error-specific
  entries by keyword/symbol match (with a gated LLM fallback);
- **`smart_file_reader`** — to read a recipe's `SCRIPT:` file for the full code.

## Two tiers, separate per language (this is what "CORE" means — a file, not a flag)
CORE is split per language so the Python analyst never sees Groovy entries (and vice
versa); each language's CORE caps independently.
- `pitfalls/CORE.<Language>.md` — promoted pitfalls, ALWAYS injected. **Fixed-size**
  (≤ 12 per language); membership is rebalanced (promotion AND demotion) by the
  Librarian. Plugin/environment-specific lessons are never kept here.
- `pitfalls/<Language>.md` — the regular pitfall library (recall-searchable).
- `recipes/CORE.<Language>.md` — featured, broadly-reusable recipes, ALWAYS injected
  (lean: name + inputs + description + SCRIPT path, **never the code**). Fixed-size
  (≤ 5 per language), rebalanced by the Librarian.
- `recipes/<Language>.md` — the regular recipe library; **one-offs are saved here**, not discarded.
- `recipes/code/`     — the verified recipe scripts (read on demand; never injected).
- `log.md` — append-only audit.

## Entry format
    <!--p:HASH seen:N lang:Groovy type:Import class:ImageCalculator scope:general kw:alias1,alias2-->
    - <one-line imperative rule — symptom AND fix>
        <minimal working snippet>
    <!--r:HASH seen:N lang:Groovy chash:CONTENT kw:...-->
    - <NAME>  [inputs: ...]
      <description>
      SCRIPT: <path under recipes/code/>

## How entries are created and curated (automatic — never by hand)
On every **verified-green** run, `learned_memory.on_success()` fires the background
**Librarian subagent** (`agents.librarian_agent`, model `gpt-5.x-mini`, off the hot
path — the task never waits) with the new recipe/pitfall plus a snapshot of the
library. The Librarian:
- **files** the new recipe (copying its code into `recipes/code/`) and the debugger/
  analyst's buffered error→fix lesson, choosing the tier (CORE vs regular);
- **dedups** — skips true duplicates and removes redundant entries;
- **rebalances CORE** periodically (every ~10 green runs): promotion from the regular
  library and demotion back out, keeping each CORE file within its fixed cap.

It mutates the wiki **only** through the deterministic `library_add_pitfall`,
`library_add_recipe`, `library_remove`, and `library_set_core` tools, so it can judge
but never garble the format or silently lose a bullet. If the model is unavailable,
`on_success` falls back to a deterministic minimal save so nothing is lost.

## Portability
Plain markdown + code files, git-tracked here — ships pre-warmed and merges across
deployments (a merge + one Librarian rebalance de-duplicates).
