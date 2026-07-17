"""
Scrapers module — Data extraction from public sources.

threads.py       — ThreadsScraperPremium (Playwright, hidden JSON, GraphQL, oEmbed)
playwright_manager.py — Singleton browser manager for Playwright
"""

from backend.scrapers.threads import (
    ThreadsScraperPremium,
    scrape_threads_profile,
    scrape_threads_posts,
)

__all__ = [
    "ThreadsScraperPremium",
    "scrape_threads_profile",
    "scrape_threads_posts",
]
