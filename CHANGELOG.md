# Changelog

## v0.4.0 - Web Crawler / Public Source Collector

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

## v0.3.0 - Redis Answer Cache

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

## [0.1.0] — Initial public PoC

- FastAPI + Streamlit
- LangGraph agent with hybrid search
- Demo Markdown ingestion
- PostgreSQL persistence (chat, feedback, agent logs)
