# 📊 Jojoba Economic News — Economic Newspaper Analytic Automation

An AI-powered **Retrieval-Augmented Generation (RAG)** system that turns a knowledge base of economic, market, and financial data into automated, data-grounded answers — delivered via REST API, a scheduled email newsletter, and an admin dashboard. The system is purpose-built as an **Economic & Investment Advisor**, strictly scoped to macroeconomics, equities, crypto, commodities, and trade/geopolitics, with built-in topic filtering, rate limiting, and source citation.

> Internally referred to as **"Jojoba Economic News"**.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [RAG Pipeline](#rag-pipeline)
  - [Agent / Guardrails Pipeline](#agent--guardrails-pipeline)
  - [Self-Refilling Question Queue](#self-refilling-question-queue)
  - [Email Delivery](#email-delivery)
  - [n8n Automation](#n8n-automation)
- [API Reference](#api-reference)
- [Setup & Installation](#setup--installation)
  - [Option A — Local (Python)](#option-a--local-python)
  - [Option B — Docker Compose](#option-b--docker-compose)
- [Environment Variables](#environment-variables)
- [Running the App](#running-the-app)
- [Admin Dashboard (Streamlit)](#admin-dashboard-streamlit)
- [Data Files](#data-files)
- [Security Notes](#security-notes)
- [Known Limitations & Notes](#known-limitations--notes)
- [Testing](#testing)
- [Roadmap Ideas](#roadmap-ideas)

---

## Overview

The project ingests a local knowledge base of economic reports, structured market data, and quantitative tables, indexes it into a vector store, and exposes a question-answering "agent" that:

1. Only answers questions strictly within **economics, markets, crypto, commodities, investment, and trade/geopolitics**.
2. Answers **only from the knowledge base** — it is explicitly instructed not to use general world knowledge and to say so when data isn't available.
3. Cites sources and appends an investment disclaimer to every substantive answer.
4. Automatically rotates through a self-replenishing **queue of questions**, so a scheduled job can ask a "new" question every run without manual curation.
5. Emails the resulting analysis (as a styled HTML newsletter) to a managed list of recipients, either directly via SMTP or through an **n8n** workflow.
6. Is monitored and administered through a **Streamlit** dashboard (manage recipients, submit ad-hoc questions, watch the queue).

It is designed to be run by a non-technical operator: start the app, let the scheduler (n8n) fire on an interval, and a newsletter goes out automatically.

---

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │              Knowledge Base              │
                         │   data/raw/*.txt (reports, tables, data)  │
                         └───────────────────┬─────────────────────┘
                                             │  load + type-aware chunking
                                             ▼
                         ┌─────────────────────────────────────────┐
                         │     RAG Layer (LlamaIndex + ChromaDB)     │
                         │  FastEmbed embeddings → Vector Index      │
                         │  Groq LLM (Llama 3.3 70B) → Query Engine  │
                         └───────────────────┬─────────────────────┘
                                             │
                                             ▼
   ┌──────────────┐        ┌─────────────────────────────────────┐        ┌─────────────────┐
   │  Validator    │──────▶│        Agent (src/services/agent)     │◀──────│ Question Queue   │
   │ topic filter  │        │  gratitude detect → validate → RAG    │        │ (txt-based, auto │
   │ guardrails    │        │  → prompt assembly → LLM → format     │        │  regenerating)   │
   └──────────────┘        └───────────────────┬───────────────────┘        └─────────────────┘
                                             │
                          ┌──────────────────┼──────────────────────┐
                          ▼                  ▼                      ▼
                 ┌────────────────┐ ┌─────────────────┐   ┌──────────────────┐
                 │  FastAPI REST   │ │ Streamlit Admin  │   │  n8n Workflows    │
                 │  /api/v1/agent  │ │ Dashboard         │   │ scheduled trigger │
                 │  middleware:    │ │ - manage emails   │   │ + webhook trigger │
                 │  auth, rate     │ │ - ask questions    │   │ → calls FastAPI   │
                 │  limit, logging │ │ - watch queue       │   │ → sends email     │
                 └────────────────┘ └─────────────────┘   └──────────────────┘
                                                                      │
                                                                      ▼
                                                            ┌──────────────────┐
                                                            │  SMTP / Email     │
                                                            │  Recipients        │
                                                            │  (HTML newsletter) │
                                                            └──────────────────┘
```

**Request flow for a single question (`/api/v1/agent/ask` or `/webhook/next`):**

1. `validate_api_key` middleware checks the `X-API-Key` header.
2. `check_rate_limit` middleware enforces a sliding-window rate limit per API key / IP.
3. `ask_agent()` runs:
   - Gratitude/small-talk short-circuit (e.g. "thanks", "ok") → canned reply, no LLM call.
   - `validate_query()` — keyword-based allow/deny list (economics-only scope).
   - `query_rag()` — semantic search against the Chroma vector index (top-5, with retry).
   - Builds a prompt from the `SYSTEM_PROMPT` template + retrieved context + question.
   - Calls the Groq-hosted LLM (`llama-3.3-70b-versatile`) to generate the answer.
   - Appends a financial disclaimer and a short "Sources" footer.
4. Result is returned as JSON and/or rendered into an HTML email and dispatched to recipients.

---

## Technology Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn (ASGI) |
| **LLM Provider** | [Groq](https://groq.com) — `llama-3.3-70b-versatile` (via `llama-index-llms-groq` / `langchain-groq`) |
| **RAG / Orchestration** | LlamaIndex (`VectorStoreIndex`, `SimpleDirectoryReader`, `SimpleNodeParser`) |
| **Embeddings** | FastEmbed — `BAAI/bge-small-en-v1.5` (local, no external embedding API call) |
| **Vector Store (active)** | ChromaDB — local persistent client (`./chroma_db`) |
| **Vector Store (provisioned, not yet wired in)** | Qdrant — runs as a Docker service; `QDRANT_URL`/`QDRANT_COLLECTION` exist in config but the current `rag.py` implementation uses Chroma, not Qdrant (see [Known Limitations](#known-limitations--notes)) |
| **Admin UI** | Streamlit |
| **Automation / Scheduling / Email-send** | n8n (workflow automation, self-hosted) |
| **Email delivery** | Python `smtplib` (STARTTLS/SSL) and/or n8n's Email Send node |
| **WhatsApp (experimental)** | [WAHA](https://github.com/devlikeapro/waha) (WhatsApp HTTP API) — wired into test scripts; not yet integrated into the main API flow |
| **Data validation** | Pydantic / pydantic-settings |
| **Retry/resilience** | Tenacity (declared dependency), manual retry loop in `query_rag` |
| **Containerization** | Docker, Docker Compose |
| **Other libs** | LangChain / LangGraph (declared, for future agentic workflows), `python-dotenv`, `python-multipart`, `aiofiles`, `email-validator`, `jinja2` |

> Several packages in `requirements.txt` (LangChain, LangGraph, Qdrant client, Ollama embeddings) are provisioned for the project's intended direction but are **not yet exercised by the current code path** — the live pipeline uses LlamaIndex + Groq + ChromaDB + FastEmbed end-to-end.

---

## Project Structure

```
Economic_Newspaper_Analityc_Automation/
├── app.py                      # Local launcher: runs FastAPI + Streamlit together
├── Dockerfile                  # Container image for the FastAPI service
├── Dockerfile.n8n              # Custom n8n image (Node + Python + n8n CLI)
├── docker-compose.yml          # Orchestrates qdrant, api, n8n, n8n-task-runners
├── requirements.txt            # Python dependencies
├── question_queue.txt          # Live queue of pending questions (auto-managed)
├── answered_questions_archive.txt  # Timestamped log of answered/retired questions
├── answered_questions.json     # JSON record of answered questions
├── debug_full.py               # Standalone debug script for the RAG/agent pipeline
│
├── data/
│   ├── raw/                    # Knowledge base ingested into the vector index
│   │   ├── structured_analysis.txt     # Pipe-delimited table: category/date/title/KPIs/sentiment
│   │   ├── deep_dive_reports.txt       # Long-form analyst-style narrative reports
│   │   └── quant_financial_data.txt    # Quantitative tables (valuations, yields, etc.)
│   ├── processing/              # Intermediate/working data (gitignored content)
│   ├── question_queue/          # Queue-related data artifacts
│   ├── email_contacts.json      # CRUD-managed list of email recipients
│   └── emails.txt
│
└── src/
    ├── main.py                  # FastAPI app factory, lifespan, routers, CORS
    │
    ├── config/
    │   ├── settings.py          # Central CONFIG dict (env-driven)
    │   └── prompts.py           # System prompt, guardrail text, canned responses
    │
    ├── middleware/
    │   ├── auth.py              # X-API-Key header validation
    │   ├── rate_limiter.py      # Sliding-window in-memory rate limiting
    │   ├── logging_middleware.py# Request/response logging + timing header
    │   └── error_middleware.py  # Global exception → JSON error handler
    │
    ├── routes/
    │   ├── agent_routes.py      # /api/v1/agent/* — ask, webhooks, emails CRUD, queue CRUD
    │   └── health_routes.py     # /api/v1/health, /health/ready, /health/live
    │
    ├── services/
    │   ├── agent.py             # Orchestrates validation → RAG → LLM → formatting
    │   ├── rag.py                # LlamaIndex/Chroma/Groq RAG pipeline + custom chunkers
    │   ├── validator.py          # Allow/forbid keyword-based topic guardrail
    │   ├── question_manager.py   # Self-refilling question queue + data-driven question generator
    │   ├── email_manager.py      # CRUD for the JSON-backed email contact list
    │   └── email_sender.py       # SMTP batch sender (STARTTLS/SSL, simulation mode)
    │
    ├── streamlit/
    │   ├── streamlit_app.py      # Admin dashboard (email mgmt + manual question submission)
    │   └── .streamlit/config.toml
    │
    ├── utils/
    │   ├── email_html.py         # Generates the branded HTML newsletter
    │   ├── helpers.py            # Text cleaning/truncation/date helpers
    │   └── logger.py             # Centralized logging setup (console + file)
    │
    ├── workflow/
    │   ├── Economic Query - Manual.json        # n8n: webhook → FastAPI → email reply
    │   └── Economic Report - Automation.json    # n8n: schedule → FastAPI /webhook/next → email
    │
    └── test/
        ├── test_request.py       # Smoke test for the /ask endpoint
        ├── test_webhook.py       # Smoke test for the /webhook(s)
        ├── test_API_key          # API key test fixture/notes
        ├── test.HTML             # Rendered email preview
        └── whatsup_test.py       # WAHA (WhatsApp) connectivity test script
```

---

## How It Works

### RAG Pipeline

Implemented in `src/services/rag.py`:

1. **Load** — `SimpleDirectoryReader` reads every file under `data/raw/`.
2. **Type-aware chunking** — instead of one generic splitter, documents are routed by filename into a dedicated chunker:
   - `structured_analysis.txt` → **row-based chunking**: each table row is paired with its header line, so a retrieved chunk is always a self-contained record.
   - `deep_dive_reports.txt` (or any "report"/"deep" file) → **paragraph-accumulation chunking** (~500 chars/chunk) with a small text overlap carried into the next chunk for continuity.
   - `quant_financial_data.txt` (or "quant"/"financial") → **table-block chunking**: contiguous `=====`/`|` delimited blocks become one chunk (a whole table), prose lines become their own chunks.
   - Anything else → **default chunking** via LlamaIndex's `SimpleNodeParser` (512 chars / 50 overlap).
3. **Embed** — FastEmbed's local `BAAI/bge-small-en-v1.5` model (no network call required for embeddings).
4. **Index** — chunks are stored in a `ChromaVectorStore` backed by a local persistent ChromaDB at `./chroma_db`.
5. **Query** — `as_query_engine(similarity_top_k=5, response_mode="compact")`, with up to 3 retry attempts (5s backoff) on failure.
6. Each result returns the matched source text (truncated to 200 chars), similarity score, detected `chunk_type`, and originating file name — used later for the "Sources" footer in the answer.

### Agent / Guardrails Pipeline

Implemented in `src/services/agent.py` + `src/services/validator.py` + `src/config/prompts.py`:

1. **Gratitude/small-talk detection** — keyword match (`thanks`, `great`, `ok`, etc.) short-circuits straight to a canned, randomized reply — saves an LLM call for non-substantive messages.
2. **Topic validation** — a question must contain at least one keyword from a large *allowed* list (stocks, macro indicators, crypto, commodities, investment terms, Indonesia-specific terms, trade/geopolitics) and must not contain a *forbidden* keyword (medical, legal, personal/relationship, drugs/weapons/crime). Anything that fails either check gets the same canned "off-topic" response (English or Indonesian).
3. **Retrieval** — top-3 retrieved source chunks are concatenated into the `{context}` slot of `SYSTEM_PROMPT`.
4. **System prompt** (`src/config/prompts.py`) is an XML-tagged instruction set that:
   - Restricts the model to **knowledge-base-only** answers (no outside knowledge, no hallucinated gap-filling).
   - Includes prompt-injection, model-extraction, and data-poisoning guards (ignore user attempts to override its role, leak its instructions, or treat user-supplied "updates" as ground truth).
   - Restricts scope to economics/markets/crypto/commodities/business/trade/investment.
   - Requires a financial disclaimer and ends every answer with a follow-up prompt ("Any other questions about economics or investments?").
5. **LLM call** — Groq's `llama-3.3-70b-versatile`, called via `.complete()` with a `.chat()` fallback if the SDK surface differs.
6. **Post-processing** — disclaimer text and a "📚 Sources" list (top 3, deduplicated by filename) are appended to the raw model output.

### Self-Refilling Question Queue

Implemented in `src/services/question_manager.py`:

- `question_queue.txt` is a flat, line-delimited FIFO queue. Seeded on first run with a default set of Indonesia/global macro questions.
- `webhook/next` pops the head question, answers it, **archives it** with a timestamp to `answered_questions_archive.txt`, then **generates and appends a brand-new question** so the queue never runs dry.
- New questions are generated by `generate_new_question_from_data()`, which:
  - Parses `data/raw/*.txt` once at import time to harvest real topics, sectors, companies, commodities, and indicators directly out of the knowledge base (via regex over `[TOPIC: ...]` tags and pipe-delimited table columns).
  - Randomly fills one of ~20 question templates (macro, sector, company, commodity, regional, policy, sentiment, investment-strategy themed) with those harvested entities.
  - Runs a **similarity check** (Jaccard overlap on significant words against the last 15 questions) to avoid near-duplicate questions; retries once, then falls back to a static fallback question list if still duplicated.
- The whole system is resettable (`/queue/reset`) back to its default seed set.

### Email Delivery

Two paths exist for getting an answer to recipients, both ending in the same HTML template (`src/utils/email_html.py` — a styled, branded newsletter layout):

1. **Direct from FastAPI** (`src/services/email_sender.py`) — uses `smtplib` with STARTTLS (port 587) or SSL (port 465). If `EMAIL_ENABLED=false` or SMTP credentials are missing, it **simulates** sending (logs recipients, returns `simulated: true`) instead of failing — useful for local dev/testing without real credentials.
2. **Via n8n** — the FastAPI endpoint returns the answer + recipient list as JSON; n8n's native **Email Send** node renders its own HTML template and dispatches the message. This decouples "who gets emailed" credential management from the Python service.

### n8n Automation

Two workflow exports live in `src/workflow/` and can be imported directly into an n8n instance:

| Workflow | Trigger | Behavior |
|---|---|---|
| **Economic Report - Automation.json** | `Schedule Trigger` (interval-based, e.g. every N seconds/hours) | Calls `POST /api/v1/agent/webhook/next` on the FastAPI service (pulls the next queued question, answers it, rotates the queue) → sends the result via n8n's Email Send node to the `email_string` returned by the API. |
| **Economic Query - Manual.json** | `Webhook` (`POST /webhook/ask`, manually triggered — e.g. from the Streamlit dashboard's "use n8n" toggle) | Forwards the incoming `{question, email}` payload to `POST /api/v1/agent/webhook` → responds to the original caller with the JSON result → also sends an email copy via n8n's Email Send node. |

Both workflows authenticate to FastAPI using the `X-API-Key` header (configured inside each n8n HTTP Request node) and reach the API container via `http://host.docker.internal:8000` (Docker Desktop) — adjust this URL for Linux Docker hosts (e.g. `--add-host=host.docker.internal:host-gateway` or use the `api` service name from `docker-compose.yml`).

---

## API Reference

All routes below (except `/`, `/api/v1/health*`) require an `X-API-Key` header. Base path: `/api/v1/agent`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root status: app metadata, agent readiness, available endpoint map |
| `GET` | `/api/v1/health` | Liveness check |
| `GET` | `/api/v1/health/ready` | Readiness check (agent initialized?) |
| `GET` | `/api/v1/health/live` | Simple alive ping |
| `POST` | `/api/v1/agent/ask` | Ask a specific question synchronously, get the answer back |
| `POST` | `/api/v1/agent/send-batch` | Ask a question **and** email the answer to a provided list of addresses |
| `POST` | `/api/v1/agent/webhook/next` | Pop the next queued question, answer it, rotate/regenerate the queue, return emails for delivery |
| `POST` | `/api/v1/agent/webhook` | Flexible webhook — accepts `question`/`message`/`text` and `email`/`phone` keys from arbitrary JSON bodies (e.g. n8n, chat platforms), answers and emails it |
| `GET` | `/api/v1/agent/status` | Full agent/RAG/queue status & feature flags |
| `GET` | `/api/v1/agent/emails` | List all email contacts |
| `GET` | `/api/v1/agent/emails/{id}` | Get a single contact |
| `POST` | `/api/v1/agent/emails` | Add a contact (`name`, `email` query params) |
| `PUT` | `/api/v1/agent/emails/{id}` | Update a contact |
| `DELETE` | `/api/v1/agent/emails/{id}` | Delete a contact |
| `GET` | `/api/v1/agent/emails/string` | Get all contact emails as one comma-separated string (for n8n) |
| `POST` | `/api/v1/agent/emails/reset` | Reset contacts to the default seed |
| `GET` | `/api/v1/agent/queue` | View the full pending question queue |
| `GET` | `/api/v1/agent/archive` | View the last 50 answered/archived questions |
| `POST` | `/api/v1/agent/queue/add` | Manually add a question to the queue |
| `POST` | `/api/v1/agent/queue/reset` | Reset the queue to its default seed |
| `POST` | `/api/v1/agent/queue/generate` | Force-generate one new data-driven question into the queue |
| `GET` | `/api/v1/agent/queue/files` | Show resolved file paths + counts for the queue/archive |
| `GET` | `/api/v1/agent/queue/data-summary` | Show harvested topics/sectors/companies/etc. used for question generation |

Interactive Swagger docs are available at **`/docs`** whenever `DEBUG=true`.

**Example — ask a question:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"question": "What is the current BI rate and its impact on the Rupiah?"}'
```

---

## Setup & Installation

### Option A — Local (Python)

**Prerequisites:** Python 3.11+, a [Groq API key](https://console.groq.com/).

```bash
git clone <repo-url>
cd Economic_Newspaper_Analityc_Automation

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file in the project root (see [Environment Variables](#environment-variables)).

Run just the API:

```bash
python -m src.main
# or
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Run **both** the API and the Streamlit dashboard together:

```bash
python app.py
```
This starts FastAPI on a background thread, waits for it to come up on port 8000, then launches Streamlit on port 8501.

### Option B — Docker Compose

**Prerequisites:** Docker + Docker Compose.

```bash
docker compose up -d --build
```

This brings up:

| Service | Port | Purpose |
|---|---|---|
| `qdrant` | 6333 / 6334 | Vector DB (provisioned; see [Known Limitations](#known-limitations--notes)) |
| `api` | 8000 | The FastAPI agent service (built from `Dockerfile`) |
| `n8n` | 5678 | Workflow automation UI (basic auth: `admin` / `password` by default — **change this**) |
| `n8n-task-runners` | — | External Python task runner for n8n's native Python code nodes |

> The `api` service expects a `.env` file to exist in the project root (`env_file: .env` in `docker-compose.yml`) — create it before running `docker compose up`.

To also run WhatsApp delivery via WAHA (experimental, not wired into the main flow), separately:

```bash
docker run -d -p 3000:3000 -e WAHA_ENV=production -v waha-data:/app/data devlikeapro/waha
```

---

## Environment Variables

Create a `.env` file at the project root. None of these are committed to source control (`.env` is in `.gitignore`).

| Variable | Default | Used by | Description |
|---|---|---|---|
| `GROQ_API_KEY` | — (required) | `rag.py`, `auth.py` | Groq API key. **Also doubles as the FastAPI `X-API-Key` value** — see [Security Notes](#security-notes) |
| `DEBUG` | `True` | `main.py`, `settings.py` | Enables `/docs`, permissive CORS |
| `API_HOST` | `0.0.0.0` | `main.py` | Uvicorn bind host |
| `API_PORT` | `8000` | `main.py` | Uvicorn bind port |
| `API_KEY` | `your-secret-api-key-12345` | `settings.py` | Declared in config but not currently the value checked by `auth.py` (which checks against `GROQ_API_KEY`) |
| `API_URL` | `http://localhost:8000/api/v1/agent` | `streamlit_app.py` | Base URL the dashboard calls |
| `APP_NAME` | `Economic Analysis System` | `settings.py` | Display name |
| `OLLAMA_URL` | `http://localhost:11434` | `settings.py` | Reserved for a local-LLM/embedding fallback (not active in current `rag.py`) |
| `QDRANT_URL` | `http://localhost:6333` | `settings.py` | Reserved for Qdrant (not active in current `rag.py`, which uses ChromaDB) |
| `QDRANT_COLLECTION` | `economic_data` | `settings.py` | Reserved Qdrant collection name |
| `DATA_DIR` | `data/raw` | `settings.py` | Knowledge base directory |
| `CHUNK_SIZE` | `1024` | `settings.py` | Declared default chunk size (the active chunkers in `rag.py` define their own sizes per document type) |
| `CHUNK_OVERLAP` | `200` | `settings.py` | Declared default overlap |
| `RATE_LIMIT` | `50` | `rate_limiter.py` | Max requests per client per `RATE_LIMIT_PERIOD` |
| `RATE_LIMIT_PERIOD` | `60` | `rate_limiter.py` | Sliding window length, in seconds |
| `EMAIL_ENABLED` | `false` | `email_sender.py` | Set `true` to actually send via SMTP; otherwise emails are simulated/logged |
| `SMTP_HOST` | `smtp.gmail.com` | `email_sender.py` | SMTP server |
| `SMTP_PORT` | `587` | `email_sender.py` | SMTP port (587 = STARTTLS, 465 = SSL) |
| `SMTP_USE_SSL` | `false` | `email_sender.py` | Force SSL connection (for port 465) |
| `SMTP_USER` | — | `email_sender.py` | SMTP login/username |
| `SMTP_PASSWORD` | — | `email_sender.py` | SMTP password / app password |
| `FROM_EMAIL` | `SMTP_USER` | `email_sender.py` | "From" address on outgoing mail |
| `N8N_WEBHOOK_URL` | `http://localhost:5678/webhook/ask` | `streamlit_app.py` | Used when the dashboard's "use n8n" delivery toggle is checked |
| `WAHA_URL` | `http://localhost:3000` | `whatsup_test.py` | WhatsApp gateway base URL (experimental) |
| `WAHA_API_KEY` | `admin` | `whatsup_test.py` | WAHA API key (experimental) |

**Minimal working `.env` for local development:**

```env
GROQ_API_KEY=gsk_your_groq_key_here
DEBUG=True
EMAIL_ENABLED=false
```

With `EMAIL_ENABLED=false`, you can exercise the entire pipeline (RAG, validation, queue rotation, dashboard) without any real SMTP credentials — emails are simply logged as "simulated".

---

## Running the App

| Goal | Command |
|---|---|
| API only | `uvicorn src.main:app --reload` |
| API + Dashboard together | `python app.py` |
| Dashboard only (API already running) | `streamlit run src/streamlit/streamlit_app.py` |
| Full stack incl. n8n + Qdrant | `docker compose up -d --build` |
| Debug/inspect the RAG+agent pipeline directly | `python debug_full.py` |
| Inspect chunking output for the knowledge base | `python -m src.services.rag` (runs `test_chunking()`) |

Once running:

- **API root:** `http://localhost:8000/`
- **Swagger docs:** `http://localhost:8000/docs` (when `DEBUG=true`)
- **Dashboard:** `http://localhost:8501`
- **n8n editor:** `http://localhost:5678`

After first boot, import the two workflow JSONs from `src/workflow/` into n8n, update the FastAPI URL/API key inside their HTTP Request nodes, and activate them.

---

## Admin Dashboard (Streamlit)

Two pages, navigable from the sidebar:

1. **📧 Email Management** — view, add, and delete email recipients; manual-refresh model (no auto-polling) so the operator controls when API calls happen; shows the recipient list pre-formatted as a comma-separated string for pasting into n8n; one-click reset to the default contact list.
2. **📝 Submit Question** — load contacts, multi-select recipients, type a free-form question, optionally add a WhatsApp phone number, choose **direct FastAPI call** or **route through n8n**, and submit. Displays per-recipient delivery status, simulation-mode warnings, and the current queue size/next-up question.

The sidebar shows a live API connectivity indicator (pings `/status` with a 2s timeout).

---

## Data Files

The knowledge base under `data/raw/` is plain text, structured for the type-aware chunkers in `rag.py`:

- **`structured_analysis.txt`** — a pipe-delimited table: `CATEGORY | DATE | TITLE | KEY_POINTS | NUMERICAL_IMPACT | SENTIMENT`, covering Indonesian macro events (BI rate decisions, inflation, PMI, VAT policy, current account, etc.).
- **`deep_dive_reports.txt`** — long-form, analyst-style narrative pieces tagged with `[DATE: ...] [TOPIC: ...]` headers (e.g. Rupiah depreciation analysis, sector deep-dives).
- **`quant_financial_data.txt`** — ASCII-table quantitative datasets (sector valuations — P/E, P/B, dividend yield, ROE; commodity prices; company financials; macro indicators), delimited with `====` separators and `|` columns.

This corpus is **synthetic/sample financial data with a strong Indonesia/ASEAN focus** intended to demonstrate the pipeline — replace it with your own licensed/curated data sources for production use.

Other persisted data:

- `data/email_contacts.json` — CRUD-managed recipient list (JSON array of `{id, name, email}`).
- `question_queue.txt` / `answered_questions_archive.txt` / `answered_questions.json` — the live question rotation and history.
- `./chroma_db/` (gitignored) — the persisted Chroma vector index, generated on first run.

---

## Security Notes

- **API authentication** is a single shared static key passed via the `X-API-Key` header, checked in `src/middleware/auth.py`. As shipped, this check compares against the **`GROQ_API_KEY`** environment variable, not a dedicated `API_KEY` secret — meaning your LLM provider key currently doubles as your API's access key. If you deploy this publicly, **issue a separate dedicated secret** for `X-API-Key` validation instead of reusing your Groq key.
- **Rate limiting** is in-memory only (`collections.defaultdict`), keyed by API key prefix or client IP — it resets on process restart and does **not** work across multiple replicas/processes. For multi-instance deployments, replace with a shared store (e.g. Redis).
- **Prompt-injection / data-poisoning guardrails** are implemented as instructions inside the system prompt (`src/config/prompts.py`), not as a separate enforcement layer — they rely on the LLM honoring the instruction, which is a reasonable first line of defense but not a hard guarantee.
- **Topic scope guardrail** (`validator.py`) is a simple keyword allow/deny list, easily bypassed by paraphrasing — adequate as a coarse filter, not a robust content-moderation system.
- CORS is wide open (`allow_origins=["*"]`) whenever `DEBUG=true` — restrict this for any non-local deployment.
- Secrets (`GROQ_API_KEY`, `SMTP_PASSWORD`, n8n basic-auth credentials, the n8n runner auth token) all currently rely on `.env` / `docker-compose.yml` plaintext values — rotate the default n8n credentials (`admin` / `password`) and the n8n runner token (`your-secret-token-change-this`) before any non-local use.

---

## Known Limitations & Notes

- **Qdrant is provisioned but not active.** `docker-compose.yml` runs a `qdrant` service and `settings.py` defines `QDRANT_URL`/`QDRANT_COLLECTION`, but the live RAG implementation (`src/services/rag.py`) uses a local **ChromaDB** persistent client instead. Either wire `rag.py` to Qdrant (the dependency `llama-index-vector-stores-qdrant` is already installed) or remove the unused `qdrant` service, depending on intended direction.
- **LangChain / LangGraph dependencies are unused by the current code path.** They're declared in `requirements.txt`, presumably for a planned multi-step/agentic workflow, but `agent.py` currently runs a straight-line pipeline (validate → retrieve → prompt → generate), not a LangGraph state machine.
- **WhatsApp/WAHA integration is experimental.** `src/test/whatsup_test.py` exercises a WAHA gateway directly, and the API/dashboard accept a `phone` field, but no service code currently sends a WhatsApp message from the main agent/email flow — phone numbers are accepted and echoed back, not dispatched.
- **`API_KEY` vs `GROQ_API_KEY` naming overlap** — see [Security Notes](#security-notes).
- **Rate limiting and the question queue are file/process-local state** — not safe to scale horizontally without external shared storage.
- The default email contact list (`email_manager.py`) seeds a placeholder contact on first run — clear/replace it via the dashboard or the `/emails/reset` and `/emails` CRUD endpoints before going live.

---

## Testing

The `src/test/` folder contains manual smoke-test scripts (not a pytest suite):

```bash
python src/test/test_request.py     # Exercise /ask directly
python src/test/test_webhook.py     # Exercise /webhook and /webhook/next
python src/test/whatsup_test.py     # Check WAHA connectivity (if running)
```

`debug_full.py` at the project root provides a broader, step-by-step manual run-through of the RAG + agent pipeline for local debugging.

---

## Roadmap Ideas

- Wire `rag.py` to the already-provisioned Qdrant service (or drop it from `docker-compose.yml` if Chroma is the long-term choice).
- Promote the LangGraph dependency into an actual multi-step agent (e.g. query decomposition, multi-hop retrieval, self-critique before responding).
- Complete the WAHA/WhatsApp delivery path so the `phone` field on `/send-batch` actually triggers a message.
- Move rate limiting and the question queue to shared storage (Redis / a real DB) for horizontal scaling.
- Separate `API_KEY` from `GROQ_API_KEY` for cleaner secret hygiene, and consider per-client keys instead of one shared secret.
- Add an automated test suite (pytest) around the validator, question generator, and chunkers.
