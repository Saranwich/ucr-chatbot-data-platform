from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    LocationAction,
    CameraAction,
    FlexMessage,
    FlexBubble,
    FlexBox,
    FlexText,
    FlexButton,
)

from app.config import GO_BACK_KEYWORD, CONFIRM_KEYWORD


def build_question_message(
    question_obj,
    show_go_back: bool = True,
    multi_select_pending: list = None,
    multi_select_max: int = None,
):
    """Build the LINE message for a survey question.

    Every question renders as a Flex bubble: the prompt plus all message-action
    options (choices, multi-select confirm, go-back) as card buttons. Native
    location / camera options can't live in a Flex button, so they go in the
    bubble's attached quick-reply bar instead.
    """
    already_selected = set(multi_select_pending or [])

    footer_buttons = []
    quick_reply_items = []

    for opt in question_obj.options:
        # Skip options the user already picked
        if opt.value and opt.value in already_selected:
            continue

        if opt.action_type == "location":
            quick_reply_items.append(QuickReplyItem(action=LocationAction(label=opt.label)))
        elif opt.action_type == "camera":
            quick_reply_items.append(QuickReplyItem(action=CameraAction(label=opt.label)))
        else:  # "message"
            action = MessageAction(label=opt.label, text=opt.value if opt.value else opt.label)
            footer_buttons.append(FlexButton(action=action, style="secondary"))

    if multi_select_pending is not None:
        count = len(multi_select_pending)
        confirm_label = f"✅ ยืนยัน ({count}/{multi_select_max})"
        footer_buttons.append(FlexButton(
            action=MessageAction(label=confirm_label, text=CONFIRM_KEYWORD),
            style="primary",
        ))

    if show_go_back:
        footer_buttons.append(FlexButton(
            action=MessageAction(label="◀️ ย้อนกลับ", text=GO_BACK_KEYWORD),
            style="link",
        ))

    body_contents = [FlexText(text=question_obj.text, wrap=True, weight="bold", size="md")]
    if multi_select_pending:
        selected_labels = ", ".join(multi_select_pending)
        body_contents.append(FlexText(
            text=f"เลือกแล้ว: {selected_labels}",
            wrap=True, size="sm", color="#888888", margin="md",
        ))

    bubble = FlexBubble(
        body=FlexBox(layout="vertical", contents=body_contents, spacing="md"),
        footer=FlexBox(layout="vertical", contents=footer_buttons, spacing="sm") if footer_buttons else None,
    )
    return FlexMessage(
        alt_text=_alt_text(question_obj.text),
        contents=bubble,
        quick_reply=QuickReply(items=quick_reply_items) if quick_reply_items else None,
    )


def _alt_text(text: str) -> str:
    """LINE caps altText at 400 chars."""
    return text if len(text) <= 400 else text[:397] + "..."


async def send_question(
    reply_token: str,
    question_obj,
    line_bot_api,
    show_go_back: bool = True,
    multi_select_pending: list = None,
    multi_select_max: int = None,
):
    message = build_question_message(
        question_obj, show_go_back, multi_select_pending, multi_select_max
    )
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=reply_token, messages=[message])
    )


async def send_text(reply_token: str, text: str, line_bot_api):
    """Reply with a plain text message."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
    )
