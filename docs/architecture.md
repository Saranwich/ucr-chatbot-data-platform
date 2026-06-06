# Architecture — Component Map (A)

> **อ่านยังไง:** กล่อง = 1 ไฟล์ `.py` · กล่องสีส้ม = ระบบภายนอก (ของนอก ไม่ใช่โค้ดเรา)
> ระบบมี **2 ซีกที่แทบไม่คุยกัน** — ตามได้จากจุดเริ่ม 2 จุด:
> - **ซีก Survey** เริ่มที่ `main.py` (รับ LINE webhook)
> - **ซีก Dashboard** เริ่มที่ `routes/dashboard.py` (REST API ให้แอดมิน)
>
> จุดร่วมเดียว = ทั้งคู่แตะ **DB เดียวกัน** และ **LINE เดียวกัน** (survey รับ/ตอบ, dashboard ดึงรูป)

```mermaid
flowchart TB
  %% ===== External boundaries =====
  LINE([LINE Messaging API]):::ext
  PG[(PostgreSQL + PostGIS)]:::ext
  ASM([AWS Secrets Manager]):::ext
  JSON[/survey JSON files/]:::ext

  subgraph WEB["Web / Entry"]
    main["main.py<br/><i>FastAPI · /callback · /health</i>"]
    dash["routes/dashboard.py<br/><i>/api/dashboard/*</i>"]
  end

  subgraph DISP["Dispatch · handlers"]
    msg["message_handler.py"]
    chat["chatbot_handler.py"]
    info["info_handler.py"]
    stat["stat_handler.py"]
    rep["report_handler.py"]
  end

  subgraph SVC["Service"]
    svc["survey_service.py<br/><i>DB + LINE IO</i>"]
    route["routing.py<br/><i>pure routing</i>"]
  end

  subgraph DATA["Data / Loader"]
    loader["survey_loader.py<br/><i>SurveyManager + schema</i>"]
    models["models/__init__.py<br/><i>SQLAlchemy</i>"]
    db["database/__init__.py<br/><i>engine · get_db</i>"]
    schemas["schemas.py"]
    auth["utils/auth.py<br/><i>JWT</i>"]
  end

  subgraph CFG["Config"]
    config["config.py<br/><i>TRIGGER_MAP · constants</i>"]
    cfgload["config_loader.py"]
  end

  %% ----- Survey half -----
  LINE -- webhook --> main
  main --> msg
  msg --> info & stat & rep & chat
  chat --> svc
  svc --> route
  svc --> loader
  svc --> models
  svc -- reply --> LINE
  route --> loader
  loader -- reads --> JSON

  %% ----- Dashboard half -----
  dash --> auth
  dash --> models
  dash --> schemas
  dash -- "image proxy" --> LINE

  %% ----- Data plumbing -----
  models --> db
  db --> PG
  main --> db

  %% ----- Config (imported on startup) -----
  main --> config
  chat --> config
  info --> config
  stat --> config
  rep --> config
  dash --> config
  config --> cfgload
  cfgload --> ASM

  classDef ext fill:#ffe8cc,stroke:#d9822b,stroke-width:2px,color:#7a4a12;
```

## โซน (layers)

| โซน | ไฟล์ | หน้าที่ |
|---|---|---|
| **Web / Entry** | `main.py`, `routes/dashboard.py` | จุดรับเข้า — webhook ของ LINE และ REST API ของแอดมิน |
| **Dispatch** | `message_handler` + `info/stat/report/chatbot_handler` | แยกข้อความตามปุ่ม Rich Menu / trigger word |
| **Service** | `survey_service` (มี IO), `routing` (pure) | state machine ของ survey — ตัดสินใจคำถามถัดไป |
| **Data / Loader** | `survey_loader`, `models`, `database`, `schemas`, `auth` | สคีมา survey, ตาราง DB, JWT |
| **Config** | `config`, `config_loader` | env / trigger map / โหลด secrets |
| **External** | LINE API, PostgreSQL+PostGIS, AWS Secrets Manager, JSON | ของนอกระบบ |
