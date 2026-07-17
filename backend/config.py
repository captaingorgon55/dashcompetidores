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
    # ─── NOSOTROS ──────────────────────────────────────────────
    "elespectador": {
        "name": "El Espectador",
        "threads_handle": "@elespectador",
        "threads_url": "https://www.threads.com/@elespectador",
        "site_url": "https://www.elespectador.com",
        "color": "#1E3A5F",
        "is_us": True,
    },
    "revistavea": {
        "name": "Revista VEA",
        "threads_handle": "@larevistavea",
        "threads_url": "https://www.threads.com/@larevistavea",
        "site_url": "https://www.elespectador.com/revista-vea/",
        "color": "#E91E63",
        "is_us": True,
    },

    # ─── REFERENTES / COMPETIDORES DIRECTOS ────────────────────
    "elpais": {
        "name": "El País (España)",
        "threads_handle": "@el_pais",
        "threads_url": "https://www.threads.com/@el_pais",
        "site_url": "https://elpais.com",
        "color": "#E53935",
        "is_us": False,
    },
    "infobae": {
        "name": "Infobae",
        "threads_handle": "@infobae",
        "threads_url": "https://www.threads.com/@infobae",
        "site_url": "https://www.infobae.com",
        "color": "#1E88E5",
        "is_us": False,
    },
    "lanacioncom": {
        "name": "La Nación (Argentina)",
        "threads_handle": "@lanacioncom",
        "threads_url": "https://www.threads.com/@lanacioncom",
        "site_url": "https://www.lanacion.com.ar",
        "color": "#00796B",
        "is_us": False,
    },
    "eltiempo": {
        "name": "El Tiempo (Colombia)",
        "threads_handle": "@eltiempo",
        "threads_url": "https://www.threads.com/@eltiempo",
        "site_url": "https://www.eltiempo.com",
        "color": "#FDD835",
        "is_us": False,
    },
    "lavanguardia": {
        "name": "La Vanguardia",
        "threads_handle": "@lavanguardia",
        "threads_url": "https://www.threads.com/@lavanguardia",
        "site_url": "https://www.lavanguardia.com",
        "color": "#8E24AA",
        "is_us": False,
    },
    "clarincom": {
        "name": "Clarín",
        "threads_handle": "@clarincom",
        "threads_url": "https://www.threads.com/@clarincom",
        "site_url": "https://www.clarin.com",
        "color": "#D32F2F",
        "is_us": False,
    },

    # ─── OTROS COMPETIDORES REGIONALES ─────────────────────────
    "eluniversalmx": {
        "name": "El Universal (México)",
        "threads_handle": "@eluniversalmx",
        "threads_url": "https://www.threads.com/@eluniversalmx",
        "site_url": "https://www.eluniversal.com.mx",
        "color": "#F57C00",
        "is_us": False,
    },
    "milenio": {
        "name": "Milenio (México)",
        "threads_handle": "@milenio",
        "threads_url": "https://www.threads.com/@milenio",
        "site_url": "https://www.milenio.com",
        "color": "#C62828",
        "is_us": False,
    },
    "globo_g1": {
        "name": "G1 (Globo)",
        "threads_handle": "@g1",
        "threads_url": "https://www.threads.com/@g1",
        "site_url": "https://g1.globo.com",
        "color": "#FF6F00",
        "is_us": False,
    },
}

# ─── Threads Scraping ────────────────────────────────────────────
THREADS_SCRAPE_INTERVAL_MINUTES = int(os.getenv("THREADS_SCRAPE_INTERVAL_MINUTES", "60"))

# Múltiples User-Agents para rotación (evitar detección)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]
USER_AGENT = USER_AGENTS[0]  # Default

# Playwright settings
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))

# Scraping rate limits
MIN_DELAY_BETWEEN_REQUESTS = float(os.getenv("MIN_DELAY_BETWEEN_REQUESTS", "2.0"))  # seconds
MAX_DELAY_BETWEEN_REQUESTS = float(os.getenv("MAX_DELAY_BETWEEN_REQUESTS", "5.0"))  # seconds
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# Proxy (opcional)
PROXY_URL = os.getenv("PROXY_URL", "")

# Meta API (opcional - requiere aprobación de Meta)
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")

# LLM Scraper (llm-scraper Node.js)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # groq, openai, openai_large
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_SCRAPER_TIMEOUT = int(os.getenv("LLM_SCRAPER_TIMEOUT", "60"))  # segundos
# Groq tiene free tier, no necesita API key para empezar
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
