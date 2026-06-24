from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import matches, predict, teams

app = FastAPI(
    title="Mundial 2026 — Tactical Intelligence API",
    description=(
        "REST API for WC2026 match results, standings, team stats, and Monte Carlo match predictions. "
        "Data sourced from worldcup26.ir (live), StatsBomb (historical xG), "
        "Rising Transfers (squads), and Onside Arena (Monte Carlo benchmark)."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(teams.router)
app.include_router(predict.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": app.version}


@app.get("/", tags=["meta"])
def root():
    return {
        "message": "Mundial 2026 API",
        "docs": "/docs",
        "endpoints": {
            "GET /health": "Health check",
            "GET /matches": "WC2026 fixtures and results",
            "GET /matches/standings": "Group stage standings",
            "GET /team/{code}/stats": "Team stats by FIFA code",
            "GET /team": "All teams overview",
            "POST /predict/winner": "Monte Carlo match prediction",
        },
    }
