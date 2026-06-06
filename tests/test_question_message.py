import pytest
from linebot.v3.messaging import (
    FlexMessage,
    LocationAction,
    CameraAction,
)

from app.utils.survey_loader import SurveyQuestion, SurveyOption
from app.services.survey_service import build_question_message
from app.config import GO_BACK_KEYWORD, CONFIRM_KEYWORD


# --- helpers -----------------------------------------------------------------

def _choice_question():
    return SurveyQuestion(
        id="q1",
        type="quick_reply",
        text="ร้อนไหม?",
        options=[
            SurveyOption(label="ร้อน", action_type="message", value="hot"),
            SurveyOption(label="เย็น", action_type="message", value="cold"),
        ],
    )


def footer_actions(flex_msg):
    """Actions of every button in a flex bubble's footer."""
    return [btn.action for btn in flex_msg.contents.footer.contents]


def body_texts(flex_msg):
    """Text of every text element in a flex bubble's body."""
    return [c.text for c in flex_msg.contents.body.contents if getattr(c, "type", None) == "text"]


def quick_reply_actions(text_msg):
    return [item.action for item in text_msg.quick_reply.items]


# --- choice questions render as Flex -----------------------------------------

def test_choice_question_renders_as_flex():
    msg = build_question_message(_choice_question(), show_go_back=False)
    assert isinstance(msg, FlexMessage)
    assert "ร้อนไหม?" in msg.alt_text
    actions = footer_actions(msg)
    assert [a.label for a in actions] == ["ร้อน", "เย็น"]
    # an option button sends its value, not its label
    assert [a.text for a in actions] == ["hot", "cold"]


def test_go_back_button_toggles():
    with_back = build_question_message(_choice_question(), show_go_back=True)
    assert GO_BACK_KEYWORD in [a.text for a in footer_actions(with_back)]

    without = build_question_message(_choice_question(), show_go_back=False)
    assert GO_BACK_KEYWORD not in [a.text for a in footer_actions(without)]


def test_multi_select_filters_selected_and_adds_confirm():
    q = SurveyQuestion(
        id="qm",
        type="multi_select",
        text="เลือกปัญหา",
        max_selections=3,
        options=[
            SurveyOption(label="ฝุ่น", action_type="message", value="dust"),
            SurveyOption(label="เสียง", action_type="message", value="noise"),
        ],
    )
    msg = build_question_message(
        q, show_go_back=True, multi_select_pending=["dust"], multi_select_max=3
    )
    texts = [a.text for a in footer_actions(msg)]
    # already-picked option is filtered out, the unpicked one remains
    assert "dust" not in texts
    assert "noise" in texts
    # a confirm button is offered
    assert CONFIRM_KEYWORD in texts
    # the running selection is echoed in the body
    assert any("dust" in t for t in body_texts(msg))


# --- location / image render as Flex with the native action in quick-reply ---
# Flex buttons can't host LocationAction/CameraAction, so those live in the
# attached quick-reply bar while the prompt + skip/go-back stay in the card.

def test_location_question_is_flex_with_location_in_quick_reply():
    q = SurveyQuestion(
        id="ql",
        type="location",
        text="ปักหมุดตำแหน่ง",
        options=[
            SurveyOption(label="แชร์ตำแหน่ง", action_type="location"),
            SurveyOption(label="ข้าม", action_type="message", value="ข้าม"),
        ],
    )
    msg = build_question_message(q, show_go_back=False)
    assert isinstance(msg, FlexMessage)
    # native location button sits in the quick-reply bar
    assert any(isinstance(a, LocationAction) for a in quick_reply_actions(msg))
    # the message-type "skip" option stays as a card button
    assert "ข้าม" in [a.text for a in footer_actions(msg)]


def test_image_question_is_flex_with_camera_in_quick_reply():
    q = SurveyQuestion(
        id="qi",
        type="image",
        text="ถ่ายรูป",
        options=[
            SurveyOption(label="เปิดกล้อง", action_type="camera"),
            SurveyOption(label="ข้าม", action_type="message", value="ข้าม"),
        ],
    )
    msg = build_question_message(q, show_go_back=False)
    assert isinstance(msg, FlexMessage)
    assert any(isinstance(a, CameraAction) for a in quick_reply_actions(msg))
    assert "ข้าม" in [a.text for a in footer_actions(msg)]
