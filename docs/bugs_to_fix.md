# UCR Chatbot: Known Bugs & Edge Cases Backlog (Tomorrow's Tasks)

This document tracks identified logic flaws and edge cases in the current chatbot survey engine (`chatbot_handler.py` and `survey_service.py`) that we need to address in Phase 2.

## 1. UX Issue: Silent Failure on Unrecognized Text
- **Trigger:** A user types random text (e.g., "สวัสดี") when they do NOT have an active survey session.
- **Result:** The bot stays completely silent.
- **Fix Required:** Add a fallback response (e.g., "กรุณาเลือกเมนูจากด้านล่างครับ") when no session is active and the text isn't a trigger word.

## 2. State Issue: Unintentional Survey Interruption
- **Trigger:** A user is halfway through an active survey and clicks "เริ่มทำแบบสำรวจ" again.
- **Result:** The system immediately deletes their current progress and starts over at Step 0 without warning.
- **Fix Required:** Check if a user has an active session *before* starting a new one. Either warn them or handle the transition safely.

## 3. Data Integrity: Invalid Data Type Input
- **Trigger:** A question asks for a Location or Image, but the user manually types text instead.
- **Result:** The system accepts the text, leading to database errors or `None` values when trying to parse coordinates from a text string.
- **Fix Required:** Implement input validation based on the question type. If the user sends text when a location was expected, ask them again politely.

## 4. Architecture Debt: Hardcoded Location ID
- **Trigger:** Changing the JSON question ID from `q1_location` to something else.
- **Result:** `survey_service.py` fails to find the location and saves `None` to the map.
- **Fix Required:** Update the engine to dynamically detect questions of type `location`.

## 5. System Stability: Database Error Handling
- **Trigger:** Database connection drops right as a user finishes.
- **Result:** SQLAlchemy throws an error, resulting in a 500 error for the user.
- **Fix Required:** Wrap finalize operations in `try/except` blocks.
