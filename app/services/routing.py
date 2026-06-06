from typing import Optional
from app.utils.survey_loader import Survey, Orchestrator


def compute_next_state(
    current_route_id: str,
    current_step: int,
    route_history: list,
    payload: dict,
    survey: Survey,
) -> dict:
    """
    Pure routing function — no DB, no LINE API.

    Given the current session state and the survey definition, returns
    what should happen next:

    action="next_question" — still inside the same route, advance one step
    action="next_route"    — current route finished, move to a new route
    action="complete"      — survey is done
    """
    current_route = survey.routes[current_route_id]
    questions = current_route.questions
    is_last_step = current_step >= len(questions) - 1

    if not is_last_step:
        next_step = current_step + 1
        return {
            "action": "next_question",
            "current_route_id": current_route_id,
            "current_step": next_step,
            "route_history": route_history,
            "next_question_id": questions[next_step],
        }

    # Route is finished — resolve what comes next from this route's exit
    next_route_id = _resolve_next_route(current_route.next, payload)

    if next_route_id is None:
        return {
            "action": "complete",
            "current_route_id": current_route_id,
            "current_step": current_step,
            "route_history": route_history,
            "next_question_id": None,
        }

    updated_history = route_history + [{"route_id": current_route_id, "step": current_step}]
    next_route = survey.routes[next_route_id]

    return {
        "action": "next_route",
        "current_route_id": next_route_id,
        "current_step": 0,
        "route_history": updated_history,
        "next_question_id": next_route.questions[0],
    }


def compute_start_route(survey: Survey, has_completed_profile) -> str:
    """
    Pure function — no DB, no LINE API.

    Decides which route a new session begins at. A returning user (profile
    already completed) skips the onstart route when its exit is a plain route
    id; otherwise everyone — new or returning — starts at onstart.
    """
    if has_completed_profile:
        after_profile = survey.routes[survey.onstart].next
        if isinstance(after_profile, str):
            return after_profile
    return survey.onstart


def compute_go_back_state(
    current_route_id: str,
    current_step: int,
    route_history: list,
    survey: Survey,
) -> dict:
    """
    Pure function — no DB, no LINE API.

    Given the current position, returns where to go when the user hits go-back:

    action="within_route"  — step back inside the same route
    action="cross_route"   — return to the last step of the previous route (pops history)
    action="at_beginning"  — already at the first question, nothing to go back to
    """
    if current_step > 0:
        prev_step = current_step - 1
        question_id = survey.routes[current_route_id].questions[prev_step]
        return {
            "action": "within_route",
            "route_id": current_route_id,
            "step": prev_step,
            "question_id": question_id,
        }

    if route_history:
        prev = route_history[-1]
        prev_route_id = prev["route_id"]
        prev_step = prev["step"]
        question_id = survey.routes[prev_route_id].questions[prev_step]
        return {
            "action": "cross_route",
            "route_id": prev_route_id,
            "step": prev_step,
            "question_id": question_id,
            "route_history": route_history[:-1],
        }

    return {"action": "at_beginning"}


def compute_multi_select_state(pending: list, new_answer: str, max_selections: int, confirm_keyword: str) -> dict:
    """
    Pure function — no DB, no LINE API.

    Handles one user tap during a multi_select question:

    action="accumulate" — answer added to pending list, not ready to advance yet
    action="confirm"    — answers are final (max reached or user sent confirm_keyword)
    action="ignore"     — user confirmed with nothing selected; do nothing

    confirm_keyword is injected by the caller (survey_service passes CONFIRM_KEYWORD
    from config) so this module stays import-clean and unit-testable.
    """
    if new_answer == confirm_keyword:
        if not pending:
            return {"action": "ignore"}
        return {"action": "confirm", "answers": list(pending)}

    updated = list(pending)
    if new_answer not in updated:
        updated.append(new_answer)

    if len(updated) >= max_selections:
        return {"action": "confirm", "answers": updated}

    return {"action": "accumulate", "pending": updated}


def _resolve_next_route(next_spec, payload: dict) -> Optional[str]:
    """Turn a route's `next` into the id of the route to walk next.

    None / "route_id" / Orchestrator  ->  route id (or None to end the survey)
    """
    if next_spec is None:
        return None
    if isinstance(next_spec, str):
        return next_spec
    if isinstance(next_spec, Orchestrator):
        for condition in next_spec.conditions:
            if _when_matches(condition.when, payload):
                return condition.goto
        return next_spec.default
    return None


def _when_matches(when: dict, payload: dict) -> bool:
    """True only if every field in `when` equals the saved answer (logical AND)."""
    return all(payload.get(field) == expected for field, expected in when.items())
