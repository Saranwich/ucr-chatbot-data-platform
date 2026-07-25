"""#114: the AI must not guess/autocomplete a place name the user typed only
part of (e.g. "ซอย 7 ย่านหนอ" -> invented "หนองจอก"). No LLM call here — just
asserting the prohibition rule actually made it into every prompt surface the
model sees, since that's the only lever we have over the model's behaviour.
"""
from app.services.ai_tool import (
    NONG_MUEANG_SYSTEM_PROMPT,
    NONG_MUEANG_BROADCAST_PROMPT,
    RECORD_COMPLAINT,
)

_BAN_PHRASE = "ห้ามเดา"


def test_system_prompt_forbids_guessing_location():
    assert _BAN_PHRASE in NONG_MUEANG_SYSTEM_PROMPT
    assert "สถานที่" in NONG_MUEANG_SYSTEM_PROMPT.split(_BAN_PHRASE, 1)[1][:200]


def test_broadcast_prompt_forbids_guessing_location():
    assert _BAN_PHRASE in NONG_MUEANG_BROADCAST_PROMPT
    assert "สถานที่" in NONG_MUEANG_BROADCAST_PROMPT.split(_BAN_PHRASE, 1)[1][:200]


def test_record_complaint_location_field_forbids_guessing():
    location_desc = RECORD_COMPLAINT["parameters"]["properties"]["location"]["description"]
    assert _BAN_PHRASE in location_desc
