from typing import Optional
from app.utils.survey_loader import Survey, Dispatcher


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
    is_last_step = current_step >= len(current_route) - 1

    if not is_last_step:
        next_step = current_step + 1
        return {
            "action": "next_question",
            "current_route_id": current_route_id,
            "current_step": next_step,
            "route_history": route_history,
            "next_question_id": current_route[next_step],
        }

    # Route is finished — resolve what comes next
    after = survey.flow.after.get(current_route_id)
    next_route_id = _resolve_next_route(after, payload)

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
        "next_question_id": next_route[0],
    }


def _resolve_next_route(after, payload: dict) -> Optional[str]:
    if after is None:
        return None
    if isinstance(after, str):
        return after
    if isinstance(after, Dispatcher):
        answer = payload.get(after.look_up_answer_of)
        return after.map.get(answer, after.default)
    return None
