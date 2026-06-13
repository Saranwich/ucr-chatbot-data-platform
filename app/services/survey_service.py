from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.survey_loader import survey_manager
from app.services.routing import (
    compute_next_state,
    compute_go_back_state,
    compute_multi_select_state,
)
from app.services import survey_repository as repo
from app.services import survey_messages as messages
from app.services.profile_messages import build_profile_invite
from app.config import GO_BACK_KEYWORD, CONFIRM_KEYWORD


def session_position_is_valid(survey, route_id: str, step: int) -> bool:
    """Can the session's saved (route, step) still be resolved against this survey?

    Survey definitions are loaded fresh from JSON at startup, but a session's
    position lives in the DB. If the file was renamed/deleted/shortened while a
    user was mid-survey, the saved position may now point at something that no
    longer exists. Return False so the caller can clear the stale session.
    """
    if survey is None:
        return False
    route = survey.routes.get(route_id)
    if route is None:
        return False
    return 0 <= step < len(route.questions)


async def start_survey_session(user_id: str, survey_version: str, reply_token: str, line_bot_api, db: AsyncSession):
    await repo.get_or_create_user(db, user_id)  # ensure the FK target exists
    await repo.archive_and_clear_session(db, user_id, status="restarted")

    # Profile ไม่อยู่ใน survey แล้ว (กรอกผ่าน Userdata LIFF) — ทุกคนเริ่มที่ onstart
    survey = survey_manager.get_survey(survey_version)
    # The trigger may point at a version that failed to load (broken/renamed JSON
    # is skipped silently at startup) or a typo'd key. Bail with a friendly reply
    # instead of crashing on survey.onstart → AttributeError → 500 → webhook retry loop.
    if survey is None:
        await messages.send_text(
            reply_token, "ขออภัย ระบบแบบสำรวจไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่ภายหลังครับ", line_bot_api
        )
        return
    start_route_id = survey.onstart

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

    # 1b. Guard against a survey file that changed since this session started.
    #     If the saved position no longer resolves, clear it and ask for a restart
    #     instead of crashing on a missing version / route / out-of-range step.
    if not session_position_is_valid(survey, active_session.current_route_id, active_session.current_step):
        await repo.archive_and_clear_session(db, user_id, status="survey_changed")
        await messages.send_text(reply_token, "เกิดข้อผิดพลาด กรุณาเริ่มทำแบบสำรวจใหม่อีกครั้ง", line_bot_api)
        return

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
        active_session.current_route_id = result["current_route_id"]
        active_session.current_step = result["current_step"]
        active_session.route_history = list(result["route_history"])
        await repo.save_session(db)
        next_question = survey_manager.get_question(survey_version, result["next_question_id"])
        await messages.send_question(reply_token, next_question, line_bot_api, show_go_back=True)

    elif result["action"] == "complete":
        await repo.finalize_report(db, active_session)

        # ยังไม่มี profile → แนบ Flex ชวนไปกรอกใน Userdata LIFF ต่อท้ายคำขอบคุณ
        user = await repo.get_or_create_user(db, user_id)
        invite = None if user.has_completed_profile else build_profile_invite()
        if invite:
            await messages.send_text_with_extras(
                reply_token, "ขอบคุณที่ร่วมรายงานข้อมูลครับ", [invite], line_bot_api
            )
        else:
            await messages.send_text(reply_token, "ขอบคุณที่ร่วมรายงานข้อมูลครับ", line_bot_api)
