from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    LocationAction,
    CameraAction
)

from app.models import User, SurveySession, CompletedReport
from app.utils.survey_loader import survey_manager
from app.services.routing import compute_next_state, compute_go_back_state, compute_multi_select_state


async def start_survey_session(user_id: str, survey_version: str, reply_token: str, line_bot_api, db: AsyncSession):
    # 1. Get or create user
    user_result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = user_result.scalars().first()
    if not user:
        user = User(lineuser_id=user_id)
        db.add(user)
        await db.flush()

    # 2. Clear any existing session (start fresh)
    session_result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    existing = session_result.scalars().first()
    if existing:
        await db.delete(existing)
        await db.flush()

    # 3. Decide which route to start at
    survey = survey_manager.get_survey(survey_version)
    flow = survey.flow

    if user.has_completed_profile:
        # Returning user: skip profile route, start at what comes after it
        after_profile = flow.after.get(flow.onstart)
        start_route_id = after_profile if isinstance(after_profile, str) else flow.onstart
    else:
        start_route_id = flow.onstart

    # 4. Create new session
    new_session = SurveySession(
        lineuser_id=user_id,
        survey_version=survey_version,
        current_route_id=start_route_id,
        current_step=0,
        route_history=[],
        payload={}
    )
    db.add(new_session)
    await db.commit()

    # 5. Send first question of the starting route (no go-back on first question)
    first_question_id = survey.routes[start_route_id][0]
    first_question = survey_manager.get_question(survey_version, first_question_id)
    if first_question:
        await send_question(reply_token, first_question, line_bot_api, show_go_back=False)


async def process_survey_answer(user_id: str, answer_data, reply_token: str, line_bot_api, db: AsyncSession):
    # 1. Load active session
    session_result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    active_session = session_result.scalars().first()

    if not active_session:
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="กรุณากดปุ่มเมนูเพื่อเริ่มแบบสำรวจครับ")]
            )
        )
        return

    survey_version = active_session.survey_version
    survey = survey_manager.get_survey(survey_version)

    # 2. Handle go-back before touching the payload
    if answer_data == "__go_back__":
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
        await db.commit()

        prev_question = survey_manager.get_question(survey_version, go_back["question_id"])
        is_first = (go_back["route_id"] == survey.flow.onstart and go_back["step"] == 0)
        await send_question(reply_token, prev_question, line_bot_api, show_go_back=not is_first)
        return

    # 3. Identify the question the user just answered
    current_route = survey.routes[active_session.current_route_id]
    current_question_id = current_route[active_session.current_step]
    current_question = survey_manager.get_question(survey_version, current_question_id)

    # 4. Handle multi_select accumulation
    if current_question and current_question.type == "multi_select":
        pending_all = (active_session.pending_multi_select or {}).copy()
        pending_this = pending_all.get(current_question_id, [])
        ms_result = compute_multi_select_state(
            pending=pending_this,
            new_answer=answer_data,
            max_selections=current_question.max_selections or 99,
        )

        if ms_result["action"] == "ignore":
            return

        if ms_result["action"] == "accumulate":
            pending_all[current_question_id] = ms_result["pending"]
            active_session.pending_multi_select = pending_all
            await db.commit()
            selected_count = len(ms_result["pending"])
            max_sel = current_question.max_selections or 99
            await send_question(
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

    # 5. Ask the routing engine where to go next
    result = compute_next_state(
        current_route_id=active_session.current_route_id,
        current_step=active_session.current_step,
        route_history=active_session.route_history or [],
        payload=payload,
        survey=survey,
    )

    # 6. Act on the routing decision
    if result["action"] == "next_question":
        active_session.current_route_id = result["current_route_id"]
        active_session.current_step = result["current_step"]
        active_session.route_history = list(result["route_history"])
        await db.commit()
        next_question = survey_manager.get_question(survey_version, result["next_question_id"])
        await send_question(reply_token, next_question, line_bot_api, show_go_back=True)

    elif result["action"] == "next_route":
        # If we just finished the profile route, mark the user as profiled
        if active_session.current_route_id == survey.flow.onstart:
            user_result = await db.execute(select(User).where(User.lineuser_id == user_id))
            user = user_result.scalars().first()
            if user:
                user.has_completed_profile = 1

        active_session.current_route_id = result["current_route_id"]
        active_session.current_step = result["current_step"]
        active_session.route_history = list(result["route_history"])
        await db.commit()
        next_question = survey_manager.get_question(survey_version, result["next_question_id"])
        await send_question(reply_token, next_question, line_bot_api, show_go_back=True)

    elif result["action"] == "complete":
        # Find the location answer anywhere in the payload
        loc_data = next(
            (v for v in payload.values() if isinstance(v, dict) and "lat" in v and "lng" in v),
            None
        )
        postgis_point = None
        if loc_data:
            postgis_point = f"SRID=4326;POINT({loc_data['lng']} {loc_data['lat']})"

        completed_report = CompletedReport(
            lineuser_id=user_id,
            survey_version=survey_version,
            payload=payload,
            location_data=postgis_point
        )
        db.add(completed_report)
        await db.delete(active_session)
        await db.commit()

        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="ขอบคุณที่ร่วมรายงานข้อมูลครับ")]
            )
        )


async def send_question(
    reply_token: str,
    question_obj,
    line_bot_api,
    show_go_back: bool = True,
    multi_select_pending: list = None,
    multi_select_max: int = None,
):
    quick_reply_items = []
    already_selected = set(multi_select_pending or [])

    for opt in question_obj.options:
        # Skip options the user already picked
        if opt.value and opt.value in already_selected:
            continue

        action = None
        if opt.action_type == "message":
            action = MessageAction(label=opt.label, text=opt.value if opt.value else opt.label)
        elif opt.action_type == "location":
            action = LocationAction(label=opt.label)
        elif opt.action_type == "camera":
            action = CameraAction(label=opt.label)

        if action:
            quick_reply_items.append(QuickReplyItem(action=action))

    if multi_select_pending is not None:
        count = len(multi_select_pending)
        confirm_label = f"✅ ยืนยัน ({count}/{multi_select_max})"
        confirm_action = MessageAction(label=confirm_label, text="__confirm_multi__")
        quick_reply_items.append(QuickReplyItem(action=confirm_action))

    if show_go_back:
        go_back_action = MessageAction(label="◀️ ย้อนกลับ", text="__go_back__")
        quick_reply_items.append(QuickReplyItem(action=go_back_action))

    # Build question text — show selected items as a running list
    text = question_obj.text
    if multi_select_pending:
        selected_labels = ", ".join(multi_select_pending)
        text = f"{text}\n\nเลือกแล้ว: {selected_labels}"

    message = TextMessage(
        text=text,
        quick_reply=QuickReply(items=quick_reply_items) if quick_reply_items else None
    )

    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[message]
        )
    )
