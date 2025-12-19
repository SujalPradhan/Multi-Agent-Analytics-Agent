# Technical Architecture Document
## Spike AI Multi-Agent Analytics System

---

## Development Philosophy

**Build incrementally. Validate early. Keep it simple.**

We approached this hackathon with a single guiding principle: each layer must work independently before integrating with the next. This reduced debugging complexity and ensured production stability.

---

## Development Phases

### Phase 1: API Gateway
**Goal:** Establish a rock-solid entry point before any business logic.

- Built FastAPI server on port 8080 (non-negotiable requirement)
- Defined strict request/response schemas with Pydantic
- Added `/health` endpoint for deployment validation
- No agent logic—just request validation and routing skeleton

**Why first?** Everything else depends on a working API. Testing agents without a stable endpoint wastes time.

---

### Phase 2: Orchestrator
**Goal:** Create the brain that decides *what* to do, not *how* to do it.

- Intent detection using LLM (analytics vs SEO vs multi-agent)
- Response format detection (natural language vs JSON)
- Lazy agent initialization (agents load only when needed)
- Task decomposition for multi-agent queries

**Key Decision:** Orchestrator doesn't execute—it delegates. This keeps responsibilities clean.

---

### Phase 3: GA4 Client + Analytics Agent
**Goal:** Connect to live Google Analytics data.

- Service account authentication via `credentials.json`
- Dynamic `propertyId` support (evaluator-safe)
- 4-stage pipeline: Parse → Validate → Execute → Synthesize
- Built-in retry logic for API failures

**Why before SEO?** GA4 is Tier 1. Get the foundation right first.

---

### Phase 4: SEO Agent + Sheets Client
**Goal:** Analyze Screaming Frog data from Google Sheets.

- **Critical:** No static CSVs—always fetch from Google Sheets API
- In-memory caching (session-scoped only)
- Semantic alias mapping for flexible column matching
- Fuzzy matching with 80% similarity threshold

**Design Choice:** Cache in memory, never to disk. Evaluators may change sheet content.

---

### Phase 5: Testing & Hardening
**Goal:** Ensure reliability under real-world conditions.

- Health check validation in deploy.sh
- Import validation before server start
- Timeout handling for LLM and external APIs
- Graceful error messages for all failure modes

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT REQUEST                          │
│                   POST /query:8080                          │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API GATEWAY                            │
│                      (main.py)                              │
│  • Request validation    • Error handling                   │
│  • Response formatting   • Health endpoint                  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                            │
│                   (orchestrator.py)                         │
│  • Intent detection (analytics/seo/multi)                   │
│  • Format detection (NL/JSON)                               │
│  • Agent routing & task decomposition                       │
└──────────┬─────────────────────────────────┬────────────────┘
           │                                 │
           ▼                                 ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│    ANALYTICS AGENT       │    │       SEO AGENT          │
│  (analytics_agent.py)    │    │    (seo_agent.py)        │
│                          │    │                          │
│  Parse → Validate →      │    │  Parse → Resolve →       │
│  Execute → Synthesize    │    │  Process → Synthesize    │
└──────────┬───────────────┘    └──────────┬───────────────┘
           │                                │
           ▼                                ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│      GA4 CLIENT          │    │    SHEETS CLIENT         │
│    (ga4_client.py)       │    │  (sheets_client.py)      │
│                          │    │                          │
│  • credentials.json      │    │  • Google Sheets API     │
│  • Dynamic propertyId    │    │  • In-memory cache only  │
│  • GA4 Data API          │    │  • No static files       │
└──────────────────────────┘    └──────────────────────────┘
                              
┌─────────────────────────────────────────────────────────────┐
│                      LLM CLIENT                             │
│                    (llm_client.py)                          │
│  • LiteLLM Proxy (http://3.110.18.218)                     │
│  • Exponential backoff for rate limits                      │
│  • Token tracking                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
Query: "What are my top 5 pages by views?"
                    │
                    ▼
         ┌─────────────────┐
         │ Intent: GA4     │
         │ Format: NL      │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Analytics Agent │
         │ extracts:       │
         │ • metric: views │
         │ • limit: 5      │
         │ • order: desc   │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ GA4 API Call    │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Natural Language│
         │ Response        │
         └─────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Lazy agent loading | Faster startup, lower memory footprint |
| In-memory cache only | Sheet content may change during evaluation |
| `python -m pip` | Cross-platform compatibility (WSL/Linux/Windows) |
| Semantic column aliases | Handles schema variations gracefully |
| Format detection in query | User intent drives output format |

---

## File Structure

```
Hackathon-Spike/
├── main.py                 # API Gateway (entry point)
├── deploy.sh               # One-command deployment
├── credentials.json        # Google service account
├── requirements.txt        # Dependencies
├── .env                    # Environment variables
│
└── src/
    ├── orchestrator.py     # Query routing & coordination
    ├── analytics_agent.py  # GA4 query processing
    ├── seo_agent.py        # SEO data analysis
    ├── ga4_client.py       # Google Analytics API client
    ├── sheets_client.py    # Google Sheets API client
    ├── llm_client.py       # LiteLLM integration
    └── response_formatter.py
```

---

## Deployment

```bash
bash deploy.sh
```

**What it does:**
1. Creates `.venv` virtual environment
2. Installs dependencies
3. Validates imports
4. Starts server on port 8080
5. Waits for health check

**Time:** ~2-3 minutes typical

---

## Testing Quick Reference

```bash
# Health check
curl http://localhost:8080/health

# GA4 Query
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"propertyId": "123456789", "query": "Top 5 pages by views"}'

# SEO Query  
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "URLs with missing meta descriptions"}'
```

---

## Constraints Honored

- ✅ Port 8080 only
- ✅ Single POST `/query` endpoint
- ✅ `credentials.json` at root
- ✅ `.venv` at root
- ✅ `deploy.sh` completes in <7 minutes
- ✅ No static CSVs for SEO data
- ✅ Evaluator-safe (dynamic propertyId)
