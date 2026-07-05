# AI Report Conversation

How a resident's free-form chat with the assistant becomes a structured community **report**. The assistant listens, asks for missing details one at a time, and commits a report by calling a tool once it has enough. One conversation can produce several reports.

## Language

### The conversation

**Assistant** (a.k.a. **น้องเมือง**):
The AI persona that talks with residents in Thai, gathers problem details, and records reports. Warm, concise, polite (ค่ะ). Its behaviour is a system prompt, not a script.
_Avoid_: bot, agent, survey, chatbot

**Resident**:
The community member chatting with the assistant over LINE. Identified by their LINE user id.
_Avoid_: user (in domain prose), respondent, customer

**Conversation**:
The ongoing multi-turn exchange between one resident and the assistant. Lives only in the session; it is not a database record.
_Avoid_: thread, dialogue, survey, flow

**Session**:
The stored transcript of one conversation — a per-resident list of turns held in Redis with a TTL. It is the assistant's short-term memory; the LLM itself is stateless, so the session is re-sent each turn (last ~10). It expires on its own; it is not the committed data.
_Avoid_: cache, history (as the store's name), state machine

**Turn**:
One message in the session — either the resident's text or the assistant's reply — tagged by role.
_Avoid_: step, question, event

### The report

**Report**:
One committed community problem — the unit of data the assistant produces. Four fields (below). Written once (currently to CSV, later Postgres); it is not editable through chat. The dashboard also surfaces reports from the LIFF form and from weather broadcasts.
_Avoid_: survey, submission, ticket, complaint (except the tool name)

**Category**:
The type of problem — **required**. e.g. ทางเท้าชำรุด, ไฟฟ้าสาธารณะ, ขยะ.
_Avoid_: type, topic, tag

**Notes**:
Free-text details of the problem in the resident's words — **required**.
_Avoid_: description, message, body, comment

**Location**:
Where the problem is — coordinates or a place name. **Optional**; skipped if the resident won't say.
_Avoid_: address, place, geo, position

**Severity**:
The impact on residents — how bad, how many affected. **Optional**.
_Avoid_: priority, urgency, level

### Committing a report

**record_complaint**:
The function-calling tool the assistant invokes to commit exactly one report, carrying the four fields. Calling it is the *only* way a report is saved — the assistant saying "จดแล้ว" in text does nothing on its own. Multiple problems in one message → one call each.
_Avoid_: save, submit, insert (as the term)

**Extraction**:
The assistant deciding a report is complete and calling `record_complaint` with the filled fields. Happens mid-conversation; the session stays alive afterwards so the resident can report more.
_Avoid_: parsing, completion, finalise

### Report sources

**Source**:
Where a report on the dashboard came from — `ai` (this conversation), `form_report` (LIFF แจ้งปัญหา page), or `broadcast` (a reply to a weather alert). All three share the map/list view.
_Avoid_: channel, origin, kind
