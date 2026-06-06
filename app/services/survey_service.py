from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.survey_loader import survey_manager
from app.services.routing import (
    compute_next_state,
    compute_go_back_state,
    compute_multi_select_state,
    compute_start_route,
)
from app.services import survey_repository as repo
from app.services import survey_messages as messages
from app.config import GO_BACK_KEYWORD, CONFIRM_KEYWORD


async def start_survey_session(user_id: str, survey_version: str, reply_token: str, line_bot_api, db: AsyncSession):
    user = await repo.get_or_create_user(db, user_id)
    await repo.clear_session(db, user_id)

    survey = survey_manager.get_survey(survey_version)
    start_route_id = compute_start_route(survey, user.has_completed_profile)

    await repo.create_session(db, user_id, survey_version, start_route_id)

    # Send the first question of the starting route (no go-back on the first question)
    first_question_id = survey.routes[start_route_id].questions[0]
    first_question = survey_manager.get_question(survey_version, first_question_id)
    if first_question:
        await messages.send_question(reply_token, first_question, line_bot_api, show_go_back=False)


async def process_survey_answer(user_id: str, answer_data, reply_token: str, line_bot_api, db: AsyncSession):
    # 1. Load active session
    active_session = await repo.load_session(db, user_id)
    if not active_session:
        await messages.send_text(reply_token, "กรุณากดปุ่มเมนูเพื่อเริ่มแบบสำรวจครับ", line_bot_api)
        return

    survey_version = active_session.survey_version
    survey = survey_manager.get_survey(survey_version)

    # 2. Handle go-back before touching the payload
    if answer_data == GO_BACK_KEYWORD:
        go_back = compute_go_back_state(
            active_session.current_route_id,
            active_session.current_step,
            active_session.route_history or [],
            survey,
        )
        if go_back["action"] == "at_beginning":
            return

        # Clear the answer for the question we're returning to so the user re-answers it
        payload = (active_session.payload or {}).copy()
        payload.pop(go_back["question_id"], None)
        active_session.payload = payload
        active_session.current_route_id = go_back["route_id"]
        active_session.current_step = go_back["step"]
        if "route_history" in go_back:
            active_session.route_history = list(go_back["route_history"])
        await repo.save_session(db)

        prev_question = survey_manager.get_question(survey_version, go_back["question_id"])
        is_first = (go_back["route_id"] == survey.onstart and go_back["step"] == 0)
        await messages.send_question(reply_token, prev_question, line_bot_api, show_go_back=not is_first)
        return

    # 3. Identify the question the user just answered
    current_route = survey.routes[active_session.current_route_id]
    current_question_id = current_route.questions[active_session.current_step]
    current_question = survey_manager.get_question(survey_version, current_question_id)

    # 4. Handle multi_select accumulation
    if current_question and current_question.type == "multi_select":
        pending_all = (active_session.pending_multi_select or {}).copy()
        pending_this = pending_all.get(current_question_id, [])
        ms_result = compute_multi_select_state(
            pending=pending_this,
            new_answer=answer_data,
            max_selections=current_question.max_selections or 99,
            confirm_keyword=CONFIRM_KEYWORD,
        )

        if ms_result["action"] == "ignore":
            return

        if ms_result["action"] == "accumulate":
            pending_all[current_question_id] = ms_result["pending"]
            active_session.pending_multi_select = pending_all
            await repo.save_session(db)
            max_sel = current_question.max_selections or 99
            await messages.send_question(
                reply_token, current_question, line_bot_api,
                show_go_back=True,
                multi_select_pending=ms_result["pending"],
                multi_select_max=max_sel,
            )
            return

        # action == "confirm" — save final answers and fall through to routing
        pending_all.pop(current_question_id, None)
        active_session.pending_multi_select = pending_all
        answer_data = ms_result["answers"]

    # 5. Handle image answer — store proxy URL instead of downloading
    if isinstance(answer_data, dict) and "image_id" in answer_data:
        answer_data["image_url"] = f"/api/dashboard/image/{answer_data['image_id']}"

    # 6. Save answer into payload (copy() so SQLAlchemy detects the change)
    payload = active_session.payload.copy() if active_session.payload else {}
    payload[current_question_id] = answer_data
    active_session.payload = payload

    # 7. Ask the routing engine where to go next
    result = compute_next_state(
        current_route_id=active_session.current_route_id,
        current_step=active_session.current_step,
        route_history=active_session.route_history or [],
        payload=payload,
        survey=survey,
    )

    # 8. Act on the routing decision
    if result["action"] == "next_question":
        active_session.current_route_id = result["current_route_id"]
        active_session.current_step = result["current_step"]
        active_session.route_history = list(result["route_history"])
        await repo.save_session(db)
        next_question = survey_manager.get_question(survey_version, result["next_question_id"])
        await messages.send_question(reply_token, next_question, line_bot_api, show_go_back=True)

    elif result["action"] == "next_route":
        # If we just finished the profile route, mark the user as profiled
        if active_session.current_route_id == survey.onstart:
            await repo.mark_profile_completed(db, user_id)

        active_session.current_route_id = result["current_route_id"]
        active_session.current_step = result["current_step"]
        active_session.route_history = list(result["route_history"])
        await repo.save_session(db)
        next_question = survey_manager.get_question(survey_version, result["next_question_id"])
        await messages.send_question(reply_token, next_question, line_bot_api, show_go_back=True)

    elif result["action"] == "complete":
        await repo.finalize_report(db, active_session)
        await messages.send_text(reply_token, "ขอบคุณที่ร่วมรายงานข้อมูลครับ", line_bot_api)
