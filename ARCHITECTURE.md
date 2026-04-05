# Subplot MVP Architecture

## Overview
Multi-tenant SaaS that gives parents daily grade reports via SMS. Parents sign up, authenticate with Aeries, add phone numbers, pick a delivery time, and get automated daily texts.

## Tech Stack (Local MVP)
- **Backend:** Python FastAPI
- **Database:** SQLite (local) → RDS Postgres (AWS)
- **Task Scheduler:** APScheduler (local) → EventBridge/Lambda (AWS)
- **SMS:** Twilio (local) → Amazon Pinpoint with toll-free numbers (AWS)
- **Scraper Isolation:** SmolVM microVMs (local) → Bedrock AgentCore Runtime (AWS)
- **Auth:** JWT tokens, bcrypt passwords
- **Frontend:** Simple HTML/JS (Jinja2 templates or static), no framework needed

## Database Schema

### users
- id (UUID, PK)
- email (unique, indexed)
- password_hash (bcrypt)
- created_at
- timezone (e.g. "America/Los_Angeles")

### students
- id (UUID, PK)
- user_id (FK → users)
- student_name (display name)
- school_district (enum: "mdusd" for now, extensible)
- aeries_email (encrypted at rest)
- aeries_password (encrypted at rest — Fernet symmetric encryption with per-tenant key)
- school_code
- student_number
- student_id (Aeries student ID)
- last_scrape_at
- last_scrape_status (success/failed/pending)
- created_at

### phone_numbers
- id (UUID, PK)
- user_id (FK → users)
- phone_number (E.164 format)
- verified (boolean, default false)
- verification_code (6-digit, nullable)
- verification_sent_at

### schedules
- id (UUID, PK)
- user_id (FK → users)
- delivery_time (TIME, e.g. "16:00")
- timezone (inherited from user or overridden)
- enabled (boolean, default true)
- days_of_week (JSON array, e.g. ["mon","tue","wed","thu","fri"])

### grade_snapshots
- id (UUID, PK)
- student_id (FK → students)
- scraped_at (timestamp)
- data (JSON — full gradebook response)
- summary_text (the human-readable report that was sent)

## API Endpoints

### Auth
- POST /api/auth/signup — { email, password, timezone }
- POST /api/auth/login — { email, password } → { access_token }

### Students
- POST /api/students — Add student { student_name, aeries_email, aeries_password, school_code, student_number, student_id }
- GET /api/students — List user's students
- DELETE /api/students/{id}
- POST /api/students/{id}/test-connection — Verify Aeries creds work (runs a scrape in smolvm)

### Phone Numbers
- POST /api/phone-numbers — { phone_number } → sends verification SMS
- POST /api/phone-numbers/verify — { phone_number, code }
- GET /api/phone-numbers — List user's numbers
- DELETE /api/phone-numbers/{id}

### Schedule
- PUT /api/schedule — { delivery_time, timezone, days_of_week, enabled }
- GET /api/schedule

### Reports
- GET /api/reports — List recent grade reports for user's students
- GET /api/reports/latest — Most recent report

## Frontend Pages (server-rendered, minimal)
- / — Landing page (marketing)
- /signup — Registration form
- /login — Login form
- /dashboard — Main dashboard after login:
  - Add/manage students
  - Add/verify phone numbers
  - Set delivery schedule
  - View recent reports
  - "Test Now" button to trigger immediate scrape

## Scraper Architecture

### Local (SmolVM)
Each scrape runs in an isolated SmolVM microVM:
1. Orchestrator reads student record from DB
2. Spawns smolvm with student's (decrypted) Aeries creds as env vars
3. VM runs Python scraper, outputs JSON to stdout
4. Orchestrator captures output, stores in grade_snapshots
5. VM is destroyed (credentials gone from memory)

### AWS (Bedrock AgentCore Runtime)
Each scrape runs in a Bedrock AgentCore session:
- Session isolation: dedicated microVM per user session
- Consumption-based pricing (~$0.0007 per scrape)
- Auto-scaling to thousands of concurrent scrapes
- Built-in observability and tracing
- Session state is ephemeral — creds never persist
- AgentCore Identity for secure credential injection
- 8-hour max session lifetime (way more than needed for a 30-sec scrape)

### Scraper Script (runs inside VM)
Same script for both local and AWS:
```python
# Reads from env: AERIES_EMAIL, AERIES_PASSWORD, SCHOOL_CODE, STUDENT_NUMBER
# 1. Login to Aeries parent portal
# 2. Fetch gradebook summary via API
# 3. Parse grades, assignments, changes
# 4. Output structured JSON to stdout
```

## SMS Delivery

### Local (Twilio)
- Twilio trial account or paid ($0.0079/SMS)
- Phone verification via Twilio Verify API
- Send grade reports via Twilio Messages API

### AWS (Pinpoint)
- Toll-free number registration
- Pinpoint SMS for delivery
- SNS for verification codes

## Scheduler

### Local (APScheduler)
- Runs inside FastAPI process
- Checks every minute for users whose delivery_time matches current time in their timezone
- For each matching user: scrape → compare → format → send SMS
- Handles timezone-aware scheduling (a user in EST picking "4 PM" gets reports at 4 PM EST)

### AWS (EventBridge + Lambda)
- EventBridge rule fires every minute
- Lambda checks which users need reports
- Triggers scrape jobs via AgentCore Runtime
- Sends SMS via Pinpoint

## Credential Security
- Aeries passwords encrypted at rest using Fernet (symmetric encryption)
- Encryption key from environment variable (SUBPLOT_ENCRYPTION_KEY)
- In SmolVM: creds passed as env vars, VM destroyed after scrape
- In AgentCore: creds injected via AgentCore Identity, session destroyed after scrape
- Never logged, never stored in plaintext

## Directory Structure
```
subplot-mvp/
├── README.md
├── ARCHITECTURE.md
├── requirements.txt
├── .env.example
├── alembic.ini                # DB migrations (future)
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app + APScheduler setup
│   ├── config.py             # Settings from env
│   ├── database.py           # SQLAlchemy + SQLite
│   ├── models.py             # ORM models
│   ├── schemas.py            # Pydantic request/response models
│   ├── auth.py               # JWT + bcrypt auth helpers
│   ├── encryption.py         # Fernet encrypt/decrypt for creds
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py           # /api/auth/*
│   │   ├── students.py       # /api/students/*
│   │   ├── phones.py         # /api/phone-numbers/*
│   │   ├── schedule.py       # /api/schedule
│   │   └── reports.py        # /api/reports/*
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scraper.py        # Orchestrator: spawn smolvm, capture output
│   │   ├── scheduler.py      # APScheduler job: check times, trigger scrapes
│   │   ├── sms.py            # Twilio SMS (local) / Pinpoint (AWS)
│   │   └── report_builder.py # Format grades into human-readable SMS
│   ├── templates/
│   │   ├── base.html
│   │   ├── landing.html
│   │   ├── signup.html
│   │   ├── login.html
│   │   └── dashboard.html
│   └── static/
│       ├── style.css
│       └── app.js
├── scraper/
│   ├── scrape.py             # The actual Aeries scraper (runs inside VM)
│   └── requirements.txt      # requests, beautifulsoup4
├── smolvm/
│   ├── Smolfile              # SmolVM image definition
│   └── build.sh              # Build packed binary
└── tests/
    ├── test_auth.py
    ├── test_students.py
    └── test_scraper.py
```

## Environment Variables
```
# App
SUBPLOT_SECRET_KEY=<random-jwt-secret>
SUBPLOT_ENCRYPTION_KEY=<fernet-key-for-cred-encryption>
DATABASE_URL=sqlite:///./subplot.db

# Twilio (local SMS)
TWILIO_ACCOUNT_SID=<sid>
TWILIO_AUTH_TOKEN=<token>
TWILIO_PHONE_NUMBER=<+1...>

# SmolVM (local scraping)
SMOLVM_BINARY=~/.local/bin/smolvm
SMOLVM_PACKED_AGENT=./smolvm/subplot-agent

# AWS (production)
AWS_REGION=us-east-1
AWS_PROFILE=personal
PINPOINT_APP_ID=<id>
AGENTCORE_ENDPOINT=<arn>
```

## Bedrock AgentCore Integration Notes

AgentCore Runtime is the AWS-managed replacement for SmolVM in production:
- **Session Isolation:** Each scrape gets a dedicated microVM (same concept as SmolVM)
- **Consumption-based pricing:** ~$0.0007/session — only pay for active CPU time, I/O wait is free
- **Framework agnostic:** Our Python scraper works as-is
- **Deployment:** Package scraper as container → push to ECR → deploy as AgentCore Runtime
- **Identity:** AgentCore Identity can manage OAuth/credential injection per-tenant
- **Observability:** Built-in tracing of each scrape execution
- **Scale:** Handles thousands of concurrent sessions automatically

### Migration Path (Local → AWS)
1. Local: SmolVM microVMs + Twilio + SQLite + APScheduler
2. AWS: AgentCore Runtime + Pinpoint + RDS Postgres + EventBridge/Lambda
3. The scraper script itself doesn't change — only the orchestrator layer

### What AgentCore Does NOT Replace
- User management / auth (still our FastAPI app)
- Scheduling logic (EventBridge replaces APScheduler)
- SMS delivery (Pinpoint replaces Twilio)
- Database (RDS replaces SQLite)
