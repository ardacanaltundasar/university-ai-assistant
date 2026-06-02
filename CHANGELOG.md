# Changelog

## Final Polish — Medeniyet Üniversitesi AI Asistanı

- Updated project naming to **Medeniyet Üniversitesi AI Asistanı**
- Clarified academic scope and non-official university application status
- Updated README and documentation for final release
- Clarified data source and generated-file policy
- Clarified system limitations and future work roadmap
- Added comprehensive validation and test workflow
- Refined documentation wording across the project
- Restored sample documents under `data/raw/samples/` for public quick-start
- Improved Redis answer cache key normalization (punctuation, casing, whitespace)
- Added Computer Engineering and faculty public source URLs to crawler configuration examples
- Added password protection for Yönetim Paneli

## v0.7.0 — RAG / Agent Evaluation Script

- Added evaluation question set (`data/evaluation/eval_questions.json`)
- Added terminal-based evaluation script (`scripts/evaluate_rag.py`)
- Added intent/tool/keyword/source/latency metrics
- Added JSON and Markdown report output under `outputs/evaluation/`
- Added optional Redis cache flush (`--flush-cache`) for clean evaluation runs

## v0.6.0 — Yönetim Paneli

- Added Streamlit Yönetim Paneli view
- Added system health overview
- Added knowledge base status
- Added Redis cache visibility
- Added PostgreSQL agent run/tool call observability
- Added operational readiness checks
- Added read-only `GET /admin/diagnostics` endpoint (no API keys in response)
- Refined Yönetim Paneli UI wording in Turkish
- Replaced interim terminology with operational readiness labels

## v0.5.0 — University Process Navigator

- Added `INCLUDE_SAMPLE_DATA` configuration to control sample document ingestion
- Documented real-data workflow with `INCLUDE_SAMPLE_DATA=false` after crawl/PDF collection
- Clarified that crawled web (`data/raw/web`) and PDF (`data/raw/pdf`) outputs are local generated data
- Added `process_guidance` intent
- Added Process Navigator tool (`backend/app/tools/process_navigator.py`)
- Added structured process guides for university workflows (step-by-step, checklist, next action)
- Added process-specific agent steps and `selected_tool`: `process_navigator`
- Added PostgreSQL tool logging for process navigation (`success` / `insufficient_sources`)
- Redis answer cache supports `process_guidance` intent keys separately

## v0.4.0 — Web Crawler / Public Source Collector

- Added public web crawler script (`scripts/crawl_website.py`)
- Added İstanbul Medeniyet University public source configuration examples (`.env.example`)
- Added direct PDF URL handling
- Added HTML content extraction
- Added PDF link discovery and download
- Added web JSON source format (`data/raw/web/`)
- Added crawler configuration variables
- Added allowed-domain restriction with subdomain support (`medeniyet.edu.tr`, `*.medeniyet.edu.tr`)
- Added web JSON ingestion support
- Documented crawler + ingestion workflow (README)

### Improved (ingestion)

- Added `INCLUDE_SAMPLE_DATA` in `.env.example` (default `true` for quick-start; `false` for real university sources)

## v0.3.0 — Redis Answer Cache

- Added Redis answer cache
- Added cache hit/miss agent steps
- Added Redis cache configuration
- Repeated questions can be served from Redis without rerunning agent workflow

## [0.2.0] — Agent Tool Routing + Open Library Resource Recommender

### Added

- Agent intent routing (`rag_question`, `resource_recommendation`, and placeholder intents)
- Open Library resource recommender tool (`backend/app/tools/resource_recommender.py`)
- LangGraph branch for `resource_recommendation` vs existing RAG pipeline
- API fields: `agent_steps`, `selected_tool`, `tool_call_logs`
- PostgreSQL logging: `selected_tool` on `AgentRun`, structured `ToolCall` for Open Library queries
- Streamlit “Agent adımları” expander with checkmark steps

### Unchanged

- Existing `/chat` contract preserved (extended response fields only)
- ChromaDB + BM25 hybrid RAG for regulation / student affairs questions
- PostgreSQL chat history and session APIs

## [0.1.0] — Initial Release

- FastAPI + Streamlit
- LangGraph agent with hybrid search
- Sample Markdown ingestion
- PostgreSQL persistence (chat, feedback, agent logs)
