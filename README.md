# Agentic Itinerary System (TBO)

Automated, deterministic, and state-driven agent system for travel itinerary management.

## Repository Structure

This repository is organized as a monorepo with distinct backend and frontend services.

```
/
├── backend/           # Python Agent System & API
│   ├── agents/        # Agent logic
│   ├── core/          # Core utilities
│   ├── server.py      # FastAPI entry point
│   └── Dockerfile
├── frontend/          # React Web Interface
│   ├── src/
│   └── Dockerfile
└── docker-compose.yml # Orchestration
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- *Or* Python 3.11+ and Node.js 18+

### Running with Docker (Recommended)

```bash
docker-compose up --build
```
- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)

### Manual Setup

**Backend:**
```bash
cd backend
pip install -r requirements.txt
python server.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
