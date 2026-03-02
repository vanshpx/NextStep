# NextStep — AI Travel Itinerary Optimizer

> **Tell us where you want to go. We'll plan the perfect trip — and adapt it when things change.**

NextStep is an AI-powered travel planning system. You describe your trip in plain English — destination, dates, budget, interests — and it builds a fully optimized, day-by-day itinerary. If something goes wrong during the trip (bad weather, crowded attraction, traffic jam), the system re-plans on the fly without losing your preferences.

The frontend is a web dashboard for travel agents to create, view, and monitor itineraries. The backend is a Python pipeline that uses mathematical optimization (FTRM + Ant Colony Optimization) to score and route attractions.

---

## What It Does

### 1. Plan Generation (Chat → Itinerary)

You provide your travel details through a guided form + free-text chat:

- **Hard constraints**: destination, dates, budget, number of travelers
- **Soft preferences**: "I love history and street food", "avoid crowded places", "kid-friendly"

The system then:

1. **Extracts constraints** from your input (NLP keyword extraction + optional LLM)
2. **Allocates budget** across accommodation, food, attractions, transport
3. **Fetches & scores attractions** using the FTRM model — each attraction gets a composite score based on your interests, proximity, cost, and time fit
4. **Optimizes the route** using Ant Colony Optimization — finds the best order to visit stops each day, minimizing travel time while maximizing satisfaction
5. **Outputs a day-by-day itinerary** with times, durations, travel legs, and budget breakdown

### 2. Real-Time Re-Optimization (During the Trip)

Once a trip is in progress, the system monitors conditions and adapts:

| Disruption | What Happens |
|---|---|
| **Crowd surge** at next stop | Reschedules to a quieter time, moves to tomorrow, or suggests alternatives |
| **Bad weather** (rain, storm, fog) | Blocks unsafe outdoor stops, re-routes to indoor alternatives |
| **Traffic jam** ahead | Defers high-value stops for later, replaces low-value ones |
| **Traveler is hungry** | Inserts a restaurant break from nearby options |
| **Traveler is tired** | Reduces remaining stops, prioritizes rest |
| **User skips/dislikes a stop** | Removes it and rebuilds the remaining plan |

Every change goes through a **confirmation gate** — the system proposes a decision, and the user (or travel agent) approves, rejects, or modifies it before anything changes.

### 3. Multi-Agent System

Four specialized agents work together through an event bus:

- **State Agent** — tracks trip position, visited stops, time, budget
- **Monitoring Agent** — watches for crowd/weather/traffic thresholds
- **Re-optimization Agent** — replans when disruptions are detected
- **Companion Agent** — handles user-facing communication and approvals

### 4. Web Dashboard (Frontend)

A Next.js web interface for travel agents:

- **Landing page** — product overview
- **Itinerary builder** — form-based trip creation (destination, dates, client details, hotels, activities)
- **Dashboard** — list of all itineraries with status, upcoming timeline, and "needs attention" alerts
- **Trip view** — day-by-day itinerary with map, activity cards, and live ops panel

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 |
| **Optimization** | FTRM scoring model, Ant Colony Optimization (ACO) |
| **Frontend** | Next.js 16, React 19, Tailwind CSS, Leaflet/Google Maps |
| **Database** | Prisma ORM + SQLite (frontend), Redis cache (backend) |
| **LLM** | Google Gemini (optional — fully functional without it) |
| **External APIs** | Google Places, TBO Hotels & Flights (all stubbable) |
| **Infrastructure** | Docker, Docker Compose |

---

## Getting Started

### Option A: Docker (Recommended)

```bash
git clone https://github.com/vanshpx/NextStep.git
cd NextStep
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend API | [http://localhost:8000](http://localhost:8000) |
| Swagger Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

### Option B: Manual Setup

**Prerequisites:** Python 3.11+ and Node.js 18+

**Backend:**

```bash
cd backend
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env    
```

**Frontend:**

```bash
cd frontend
npm install
npx prisma generate
```

---

## Usage

### Generate an Itinerary (CLI)

The CLI is the fastest way to try the pipeline. No API keys needed — all external services are stubbed by default.

```bash
cd backend

# Quick run — uses default stub data for Delhi
python main.py

# Interactive — answer form questions + describe preferences in chat
python main.py --chat

# Full experience — generate itinerary, then simulate disruptions
python main.py --chat --reoptimize
```

**Example session:**

```
Destination city: Jaipur
Departure city: Delhi
Departure date (YYYY-MM-DD): 2026-04-01
Return date (YYYY-MM-DD): 2026-04-04
Number of adults: 2
Total budget (INR): 50000

Describe your preferences (type 'done' when finished):
> We love history and architecture. Want to see old forts and palaces.
> Also interested in local street food and markets.
> done

[Stage 1] Constraints extracted: destination=jaipur, 3 days, budget=50000 INR
[Stage 2] Budget allocated: Accommodation 35%, Attractions 20%, Food 15% ...
[Stage 3] 12 attractions scored and ranked
[Stage 4] ACO optimized route across 3 days

=== DAY 1 (2026-04-01) ===
  09:00  Amber Fort (120 min) — score: 0.87
  11:30  Nahargarh Fort (90 min) — score: 0.82
  13:30  Lunch break
  ...
```

### Interactive Re-Optimizer

After generating an itinerary, the `--reoptimize` flag drops you into an interactive session:

```
Commands:
  crowd <pct>     — Simulate crowd at next stop (e.g., crowd 80)
  weather <cond>  — Simulate weather (e.g., weather thunderstorm)
  traffic <pct>   — Simulate traffic delay (e.g., traffic 60)
  skip            — Skip the next stop
  replace         — Replace next stop with alternative
  hungry          — Trigger hunger disruption
  tired           — Trigger fatigue disruption
  continue        — Advance to next stop normally
  approve/reject  — Respond to pending decisions
  summary         — Show current trip state
  end             — Exit
```

### Run the API Server

```bash
cd backend
uvicorn api.server:app --reload --port 8000
```

### Run the Frontend

```bash
cd frontend
npm run dev
# Open http://localhost:3000
```

### Run the Demo (No Input Needed)

A scripted walkthrough of 6 re-optimization scenarios with plain-English explanations:

```bash
cd backend
python demo_reoptimizer.py
```

---

## API Endpoints

All endpoints are prefixed with `/v1`. Full Swagger docs available at `/docs` when the server is running.

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/health` | Health check |
| `POST` | `/v1/itinerary/generate` | Generate itinerary from constraints |
| `POST` | `/v1/reoptimize/advance` | Advance trip to the next stop |
| `POST` | `/v1/reoptimize/event` | Inject a disruption event (skip, replace, etc.) |
| `POST` | `/v1/reoptimize/check` | Check environmental conditions (crowd/weather/traffic) |
| `POST` | `/v1/reoptimize/resolve` | Approve, reject, or modify a pending decision |
| `GET` | `/v1/reoptimize/summary/{id}` | Get current session state and trip summary |

---

## Testing

```bash
cd backend

# Full 8-part regression suite — exit code 0 means all pass
# No API keys needed (runs entirely in stub mode)
USE_STUB_LLM=true python test_full_pipeline.py
```

| Part | What It Tests |
|---|---|
| 1 | Chat intake — constraint extraction from form + free text |
| 2 | Budget planning — allocation across categories |
| 3 | Recommendation — attraction scoring and ranking |
| 4 | Route planning — ACO optimization, day scheduling |
| 5 | Memory — short-term session log, long-term user profile |
| 6 | Full pipeline — end-to-end from chat to itinerary |
| 7 | Re-optimization — all disruption types and advisors |
| 8 | Multi-agent orchestrator — agent coordination and confirmation gates |

---

## Configuration

All settings are via environment variables. Copy `backend/.env.example` → `backend/.env`.

**By default, everything runs in stub mode — no API keys needed.**

| Variable | Default | What It Controls |
|---|---|---|
| `USE_STUB_LLM` | `true` | Use dummy LLM instead of Gemini |
| `USE_STUB_ATTRACTIONS` | `true` | Use hardcoded attraction data instead of Google Places |
| `USE_STUB_HOTELS` | `true` | Use dummy hotel data instead of TBO API |
| `USE_STUB_RESTAURANTS` | `true` | Use dummy restaurant data |
| `USE_STUB_FLIGHTS` | `true` | Use dummy flight data instead of TBO API |
| `LLM_API_KEY` | — | Your Google Gemini API key |
| `GOOGLE_PLACES_API_KEY` | — | Google Places API key (enables any city worldwide) |
| `TBO_USERNAME` / `TBO_PASSWORD` | — | TBO API credentials for live hotel/flight data |

### Supported Cities

**Stub mode (offline, no API key):** Agra, Bangalore, Delhi, Goa, Jaipur, Mumbai

**Live mode (with `GOOGLE_PLACES_API_KEY`):** Any city in the world

---

## Repository Structure

```
NextStep/
├── backend/                        Python optimization engine
│   ├── main.py                     CLI entry point (pipeline + re-optimizer)
│   ├── config.py                   All environment configuration
│   ├── requirements.txt            Python dependencies
│   ├── Dockerfile                  Container build
│   ├── .env.example                Environment variable template
│   ├── api/
│   │   ├── server.py               FastAPI application
│   │   └── routes/                 Health, itinerary, re-optimize endpoints
│   ├── agents/                     Multi-agent system
│   │   ├── state_agent.py          Trip state tracking
│   │   ├── monitoring_agent.py     Environmental condition monitoring
│   │   ├── reoptimization_agent.py Disruption response
│   │   └── companion_agent.py      User-facing communication
│   ├── orchestrator/               Agent coordination
│   │   ├── orchestrator.py         Central agent dispatcher
│   │   └── confirmation_gate.py    User approval before state changes
│   ├── modules/
│   │   ├── input/                  Chat intake & constraint extraction
│   │   ├── planning/               Budget allocation, route optimization, scoring
│   │   ├── recommendation/         Attraction, hotel, restaurant, flight ranking
│   │   ├── optimization/           FTRM satisfaction, ACO, constraint registry
│   │   ├── reoptimization/         Session manager, event handlers, advisors
│   │   │   ├── session.py          Top-level re-optimization facade
│   │   │   ├── trip_state.py       Live position & visited tracking
│   │   │   ├── event_handler.py    Disruption event routing
│   │   │   ├── condition_monitor.py Threshold detection
│   │   │   ├── crowd_advisory.py   Crowd surge strategies
│   │   │   ├── weather_advisor.py  Weather severity & indoor routing
│   │   │   ├── traffic_advisor.py  Traffic delay handling
│   │   │   └── ...                 Local repair, alternatives, hunger/fatigue
│   │   ├── memory/                 Short-term, long-term, disruption memory
│   │   ├── tool_usage/             External data tools (attractions, hotels, etc.)
│   │   ├── observability/          Structured JSONL logging & replay
│   │   └── validation/             Pipeline state invariants
│   ├── schemas/                    Pydantic data models
│   │   ├── constraints.py          Hard/Soft/Commonsense constraints
│   │   ├── itinerary.py            Itinerary, DayPlan, RoutePoint
│   │   └── ftrm.py                 FTRM parameters (α, β, ρ, weights)
│   ├── core/                       Shared enums, events, models
│   ├── infrastructure/             Event bus for agent communication
│   ├── scripts/                    Bootstrap & migration utilities
│   ├── architecture/               Architecture & math documentation
│   │   ├── ARCHITECTURE.md         System architecture
│   │   ├── AGENT_ARCHITECTURE.md   Multi-agent design
│   │   ├── SYSTEM_WORKFLOW.md      End-to-end pipeline workflow
│   │   └── MATH.md                 All mathematical formulas
│   ├── tests/                      State invariant tests
│   ├── test_full_pipeline.py       8-part regression suite
│   └── demo_reoptimizer.py         Scripted demo of 6 disruption scenarios
├── frontend/                       Next.js 16 web dashboard
│   ├── src/
│   │   ├── app/                    App router pages
│   │   │   ├── page.tsx            Landing page
│   │   │   ├── dashboard/          Agent dashboard (itinerary list, ops panel)
│   │   │   │   ├── create/         New itinerary builder
│   │   │   │   ├── edit/           Edit existing itinerary
│   │   │   │   └── trips/          Trip management
│   │   │   └── view/[id]/          Detailed trip view with map
│   │   ├── components/             UI components
│   │   │   ├── builder/            Itinerary creation forms
│   │   │   ├── dashboard/          Dashboard panels and tables
│   │   │   ├── landing/            Hero section, feature cards
│   │   │   └── ui/                 Shared buttons, inputs, cards
│   │   ├── services/               API client (re-optimization calls)
│   │   ├── context/                React context (itinerary state)
│   │   └── hooks/                  Custom React hooks
│   └── prisma/                     Database schema & migrations
├── docker-compose.yml              Run both services
└── LICENSE                         MIT License
```

---

## How It Works (Technical Overview)

### The FTRM Scoring Model

Every attraction gets a satisfaction score $S_{pti} \in [0,1]$ for each time slot:

$$S_{pti} = HC_{pti} \times SC_{pti}$$

- **$HC_{pti}$** (Hard Constraints) — binary gate. If the attraction is closed, too far, or violates accessibility requirements → score = 0.
- **$SC_{pti}$** (Soft Constraints) — weighted sum of interest match, proximity, cost fit, time fit, and popularity. Higher = better match for the traveler.

### Ant Colony Optimization (ACO)

Once attractions are scored, ACO finds the optimal visiting order:

1. Virtual "ants" explore different route permutations
2. Each ant picks the next stop based on: $P_{ij} = \frac{\tau_{ij}^\alpha \cdot \eta_{ij}^\beta}{\sum \tau_{ij}^\alpha \cdot \eta_{ij}^\beta}$
   - $\tau$ = pheromone (learned from previous good routes)
   - $\eta$ = heuristic (attraction score / travel time)
3. Best routes get more pheromone → convergence on optimal solution
4. Repeated per day, respecting time budget (default: 10 hours/day)

Full mathematical details → [MATH.md](backend/architecture/MATH.md)

---

## Documentation

All architecture docs live in `backend/architecture/`:

| Document | Description |
|---|---|
| [MATH.md](backend/architecture/MATH.md) | Every equation: FTRM scoring, ACO, constraint checks, re-optimization thresholds |
| [ARCHITECTURE.md](backend/architecture/ARCHITECTURE.md) | Full system architecture — all modules, data flow, pipeline stages |
| [SYSTEM_WORKFLOW.md](backend/architecture/SYSTEM_WORKFLOW.md) | End-to-end walkthrough from user input to final itinerary |
| [AGENT_ARCHITECTURE.md](backend/architecture/AGENT_ARCHITECTURE.md) | Multi-agent design — agents, event bus, confirmation gates |

---

## License

MIT — see [LICENSE](LICENSE) for details.
