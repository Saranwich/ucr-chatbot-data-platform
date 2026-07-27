"""#120: the no-guessing rule (#114/PR #119) must stay scoped to *facts* — mainly
place names — without telling the model to stop doing its required extraction work:
category is required, severity is AI-graded from impact (#113) and title is a summary,
all three inherently go beyond the user's literal words. No LLM call here — the prompt
text is the only lever we have, so we assert on it (same approach as
test_ai_no_location_guessing.py, which guards the other direction).
"""
from app.services.ai_tool import (
    NONG_MUEANG_SYSTEM_PROMPT,
    NONG_MUEANG_BROADCAST_PROMPT,
    RECORD_COMPLAINT,
)

_ALLOW_PHRASE = "ไม่ถือว่าเดา"


def _allowance_clause(prompt: str) -> str:
    """ข้อความรอบๆ วลีอนุญาต — กันเทสต์ผ่านเพราะคำไปโผล่คนละที่ในพรอมป์ต"""
    idx = prompt.index(_ALLOW_PHRASE)
    return prompt[max(0, idx - 250): idx + 250]


def test_system_prompt_still_allows_category_severity_title():
    assert _ALLOW_PHRASE in NONG_MUEANG_SYSTEM_PROMPT
    clause = _allowance_clause(NONG_MUEANG_SYSTEM_PROMPT)
    for field in ("category", "severity", "title"):
        assert field in clause


def test_broadcast_prompt_still_allows_category_severity_title():
    assert _ALLOW_PHRASE in NONG_MUEANG_BROADCAST_PROMPT
    clause = _allowance_clause(NONG_MUEANG_BROADCAST_PROMPT)
    for field in ("category", "severity", "title"):
        assert field in clause


def test_no_guessing_rule_does_not_cover_the_extracted_fields():
    """กฎห้ามเดาต้องไม่เหมารวมหมวดหมู่/หัวข้อ/รายละเอียด (ถ้อยคำเดิมที่ทำให้ #120 เกิด)"""
    assert "รวมถึงรายละเอียด/หัวข้อ/หมวดหมู่ด้วย" not in NONG_MUEANG_SYSTEM_PROMPT
    assert "รวมถึงรายละเอียด/หัวข้อ/หมวดหมู่ด้วย" not in NONG_MUEANG_BROADCAST_PROMPT


def test_category_field_says_classifying_is_not_guessing():
    """tool spec คือสิ่งที่โมเดลเห็นตอนจะเรียกจริง — category required ห้ามให้มันลังเล"""
    assert _ALLOW_PHRASE in RECORD_COMPLAINT["parameters"]["properties"]["category"]["description"]
