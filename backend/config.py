"""
Configuration module for the Competitor Dashboard.
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ─── Project Paths ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DB_PATH = BACKEND_DIR / "data" / "dashboard.db"

# ─── Database ────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

# ─── Server ──────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ─── Google APIs (OAuth2) ────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
SITE_URL = os.getenv("SITE_URL", "sc-domain:elespectador.com")  # e.g. "sc-domain:elespectador.com"

# ─── Default Competitors ─────────────────────────────────────────
DEFAULT_COMPETITORS = {
    "elespectador": {
        "name": "El Espectador",
        "threads_handle": "@elespectador",
        "threads_url": "https://www.threads.net/@elespectador",
        "site_url": "https://www.elespectador.com",
        "color": "#1E3A5F",
        "is_us": True,
    },
    "revistavea": {
        "name": "Revista VEA",
        "threads_handle": "@larevistavea",
        "threads_url": "https://www.threads.net/@larevistavea",
        "site_url": "https://www.elespectador.com/revista-vea/",
        "color": "#E91E63",
        "is_us": True,
    },
    "globo_g1": {
        "name": "G1 (Globo)",
        "threads_handle": "@g1",
        "threads_url": "https://www.threads.net/@g1",
        "site_url": "https://g1.globo.com",
        "color": "#FF6F00",
        "is_us": False,
    },
    "lanacion": {
        "name": "La Nación",
        "threads_handle": "@lanacion",
        "threads_url": "https://www.threads.net/@lanacion",
        "site_url": "https://www.lanacion.com.ar",
        "color": "#00796B",
        "is_us": False,
    },
    "clarin": {
        "name": "Clarín",
        "threads_handle": "@clarin",
        "threads_url": "https://www.threads.net/@clarin",
        "site_url": "https://www.clarin.com",
        "color": "#D32F2F",
        "is_us": False,
    },
}

# ─── Threads Scraping ────────────────────────────────────────────
THREADS_SCRAPE_INTERVAL_MINUTES = int(os.getenv("THREADS_SCRAPE_INTERVAL_MINUTES", "60"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
