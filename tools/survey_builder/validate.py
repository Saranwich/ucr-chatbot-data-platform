#!/usr/bin/env python3
"""Validate survey JSON files against the *real* bot schema.

This is the authoritative gate for anything the survey builder exports. It
imports the same Pydantic `Survey` model the running bot loads at startup
(``app.utils.survey_loader``), so there is no second schema to drift out of
sync. On top of Pydantic's shape checks it runs the referential-integrity
checks the bot relies on at runtime but never validates up front (dangling
``goto`` targets, missing questions, unreachable routes, ...).

Usage:
    # validate one file
    python tools/survey_builder/validate.py app/data/surveys/fdg140626.json

    # validate every survey in the default directory
    python tools/survey_builder/validate.py

Exit code is 0 when every file passes, 1 otherwise. Warnings never fail the
run — only hard errors do.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root is two levels up: tools/survey_builder/validate.py -> repo/
REPO_ROOT = Path(__file__).resolve().parents[2]
SURVEY_DIR = REPO_ROOT / "app" / "data" / "surveys"
sys.path.insert(0, str(REPO_ROOT))

from app.utils.survey_loader import Survey  # noqa: E402  (after sys.path tweak)

# Vocabulary the bot actually understands (see app/services/survey_messages.py).
KNOWN_QUESTION_TYPES = {"quick_reply", "location", "image", "multi_select"}
KNOWN_ACTION_TYPES = {"message", "location", "camera"}
# Top-level keys that are builder-only metadata, ignored by the bot.
BUILDER_KEYS = {"_builder"}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _semantic_checks(survey: Survey, raw: dict) -> tuple[list[str], list[str]]:
    """Cross-reference checks Pydantic can't express. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    routes = survey.routes
    questions = survey.questions

    # onstart must point at a real route
    if survey.onstart not in routes:
        errors.append(f"onstart '{survey.onstart}' is not a defined route")

    # question dict key should match the question's own id
    for key, q in questions.items():
        if q.id != key:
            warnings.append(f"question key '{key}' != its id '{q.id}' (the bot keys by '{key}')")
        if q.type not in KNOWN_QUESTION_TYPES:
            errors.append(f"question '{key}' has unknown type '{q.type}'")
        for opt in q.options:
            if opt.action_type not in KNOWN_ACTION_TYPES:
                errors.append(f"question '{key}' option '{opt.label}' has unknown action_type '{opt.action_type}'")
        if q.type in ("quick_reply", "multi_select") and not q.options:
            warnings.append(f"question '{key}' is {q.type} but has no options")
        if q.type == "multi_select" and q.max_selections is None:
            warnings.append(f"question '{key}' is multi_select without max_selections")

    referenced_questions: set[str] = set()
    for rid, route in routes.items():
        # every question a route lists must exist
        for qid in route.questions:
            referenced_questions.add(qid)
            if qid not in questions:
                errors.append(f"route '{rid}' references undefined question '{qid}'")

        nxt = route.next
        if nxt is None:
            continue
        if isinstance(nxt, str):
            if nxt not in routes:
                errors.append(f"route '{rid}' next -> undefined route '{nxt}'")
        else:  # Orchestrator
            for i, cond in enumerate(nxt.conditions):
                for field in cond.when:
                    if field not in questions:
                        warnings.append(
                            f"route '{rid}' condition #{i + 1} tests unknown field '{field}'"
                        )
                if cond.goto is not None and cond.goto not in routes:
                    errors.append(f"route '{rid}' condition #{i + 1} goto -> undefined route '{cond.goto}'")
            if nxt.default is not None and nxt.default not in routes:
                errors.append(f"route '{rid}' default -> undefined route '{nxt.default}'")

    # reachability from onstart
    reachable: set[str] = set()
    if survey.onstart in routes:
        stack = [survey.onstart]
        while stack:
            rid = stack.pop()
            if rid in reachable:
                continue
            reachable.add(rid)
            nxt = routes[rid].next
            if isinstance(nxt, str) and nxt in routes:
                stack.append(nxt)
            elif nxt is not None and not isinstance(nxt, str):
                for cond in nxt.conditions:
                    if cond.goto in routes:
                        stack.append(cond.goto)
                if nxt.default in routes:
                    stack.append(nxt.default)
    for rid in routes:
        if rid not in reachable:
            warnings.append(f"route '{rid}' is unreachable from onstart '{survey.onstart}'")

    # questions defined but never used by any route
    for qid in questions:
        if qid not in referenced_questions:
            warnings.append(f"question '{qid}' is defined but never used by any route")

    # surface unexpected top-level keys (typos), but allow builder metadata
    known_top = {"version", "onstart", "questions", "routes"} | BUILDER_KEYS
    for key in raw:
        if key not in known_top:
            warnings.append(f"unexpected top-level key '{key}' (ignored by the bot)")

    return errors, warnings


def validate_file(path: Path) -> bool:
    """Validate one survey file. Prints a report and returns True if it passed."""
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"{RED}✗ {rel}{RESET}\n    invalid JSON: {e}")
        return False

    try:
        survey = Survey(**raw)
    except Exception as e:  # pydantic ValidationError or otherwise
        print(f"{RED}✗ {rel}{RESET}\n    schema error: {e}")
        return False

    errors, warnings = _semantic_checks(survey, raw)

    if errors:
        print(f"{RED}✗ {rel}{RESET}  (version '{survey.version}')")
        for msg in errors:
            print(f"    {RED}error:{RESET} {msg}")
        for msg in warnings:
            print(f"    {YELLOW}warn:{RESET}  {msg}")
        return False

    print(f"{GREEN}✓ {rel}{RESET}  (version '{survey.version}', "
          f"{len(survey.routes)} routes, {len(survey.questions)} questions)")
    for msg in warnings:
        print(f"    {YELLOW}warn:{RESET}  {msg}")
    return True


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args:
        targets = [Path(a).resolve() for a in args]
    else:
        if not SURVEY_DIR.is_dir():
            print(f"{RED}survey directory not found: {SURVEY_DIR}{RESET}")
            return 1
        targets = sorted(SURVEY_DIR.glob("*.json"))
        if not targets:
            print(f"{YELLOW}no survey files in {SURVEY_DIR}{RESET}")
            return 0
        print(f"{DIM}validating {len(targets)} survey(s) in {SURVEY_DIR.relative_to(REPO_ROOT)}{RESET}\n")

    results = [validate_file(t) for t in targets]
    passed, total = sum(results), len(results)
    print()
    if passed == total:
        print(f"{GREEN}all {total} file(s) passed{RESET}")
        return 0
    print(f"{RED}{total - passed} of {total} file(s) failed{RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
