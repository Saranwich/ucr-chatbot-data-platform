# Survey Builder

A small, offline, drag-and-drop editor for authoring the survey JSON files the
bot loads from `app/data/surveys/`. Built for **maintainers who already have the
repo cloned** — it lives in-repo so the schema can never drift from the bot.

```
tools/survey_builder/
├── index.html      ← the editor (open directly in a browser, no server)
├── validate.py     ← authoritative CLI validator (uses the bot's real schema)
└── vendor/         ← Drawflow (graph lib), vendored so it works offline
```

## Workflow

1. **Open** `tools/survey_builder/index.html` in any browser (double-click it).
   No server, no build step, no internet needed.
2. **Build** the survey:
   - Set a **version** (this becomes the filename + the key the bot loads by).
   - Each box on the canvas is a **route**. Drag boxes around freely.
   - Click **+ คำถาม** in a box to add a question; click a question to edit its
     text, type, and options in the right-hand panel.
   - Set each route's **exit** at the bottom of its box:
     - **จบ** — ends the survey.
     - **ไป route เดียว** — always goes to one route (you can also drag a wire
       from the box's right dot to the target box).
     - **แยกตามคำตอบ** — branch: `if <question> = <answer> → <route>`, with a
       `default` fallback. Targets are picked from the dropdowns; the wires draw
       themselves.
   - Use the **📱 Preview** tab to see how a question renders as a LINE bubble,
     and the **✓ ตรวจ** tab for a quick in-browser sanity check.
3. **Export JSON** → downloads `<version>.json`. Move it into
   `app/data/surveys/`.
4. **Validate** (the authoritative check):
   ```bash
   python tools/survey_builder/validate.py app/data/surveys/<version>.json
   # or validate everything:
   python tools/survey_builder/validate.py
   ```
5. **Wire up the trigger**: add a keyword in `app/config.py` →
   `SURVEY_TRIGGER_MAP`: `"<keyword>": "<version>"`.
6. **Restart** the server — the new JSON is picked up at startup.

To edit an existing survey later, use **⬆ Import** and pick its `.json`; the
canvas layout is restored too (see below).

## How layout is stored

Box positions are saved under a top-level `_builder` key inside the same JSON:

```json
{ "version": "...", "onstart": "...", "questions": {...}, "routes": {...},
  "_builder": { "positions": { "start_route": { "x": 120, "y": 120 } } } }
```

The bot's Pydantic schema **ignores** unknown top-level keys, so `_builder` rides
along harmlessly in the live file and the editor can reopen the exact layout.
No sidecar file to keep in sync.

## Why a CLI validator instead of validating in the browser

`validate.py` imports the *same* `Survey` model the bot loads at startup
(`app.utils.survey_loader`), so there is **one schema, no duplicate to drift**.
On top of Pydantic's shape checks it catches the referential bugs the bot would
only hit at runtime: dangling `goto`/`next` targets, a missing `onstart`,
questions a route references but doesn't define, and unreachable routes. The
browser's **✓ ตรวจ** tab is a convenience mirror only — `validate.py` is the
gate before you commit.

## Notes / limits

- Branch conditions use a **single field** per condition (`if Q = value`), which
  covers every existing survey. The schema also supports multi-field AND
  conditions; hand-edit the JSON for those rare cases.
- Vendored Drawflow is MIT-licensed (`vendor/drawflow.min.js`, v0.0.59).
