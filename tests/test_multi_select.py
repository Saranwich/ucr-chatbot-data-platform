import pytest
from app.services.routing import compute_multi_select_state


# --- Behavior 1: first selection accumulates, does not advance ---

def test_first_selection_accumulates():
    result = compute_multi_select_state(
        pending=[], new_answer="อยู่ลำบาก", max_selections=2
    )
    assert result["action"] == "accumulate"
    assert result["pending"] == ["อยู่ลำบาก"]


# --- Behavior 2: reaching max auto-confirms ---

def test_reaching_max_auto_confirms():
    result = compute_multi_select_state(
        pending=["อยู่ลำบาก"], new_answer="ไม่ปลอดภัย", max_selections=2
    )
    assert result["action"] == "confirm"
    assert result["answers"] == ["อยู่ลำบาก", "ไม่ปลอดภัย"]


# --- Behavior 3: explicit confirm with partial selections ---

def test_explicit_confirm_saves_partial():
    result = compute_multi_select_state(
        pending=["อยู่ลำบาก"], new_answer="__confirm_multi__", max_selections=3
    )
    assert result["action"] == "confirm"
    assert result["answers"] == ["อยู่ลำบาก"]


# --- Behavior 4: confirm with nothing selected is ignored ---

def test_confirm_with_empty_pending_is_ignored():
    result = compute_multi_select_state(
        pending=[], new_answer="__confirm_multi__", max_selections=2
    )
    assert result["action"] == "ignore"


# --- Behavior 5: selecting same option twice is deduplicated ---

def test_duplicate_selection_is_deduplicated():
    result = compute_multi_select_state(
        pending=["อยู่ลำบาก"], new_answer="อยู่ลำบาก", max_selections=2
    )
    assert result["action"] == "accumulate"
    assert result["pending"].count("อยู่ลำบาก") == 1
