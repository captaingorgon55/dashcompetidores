"""
Google Search Console API integration.

Fetches search performance + Google Discover data.
Requires OAuth2 credentials configured in environment.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.config import SITE_URL

logger = logging.getLogger(__name__)


class SearchConsoleClient:
    """Client for Google Search Console API."""

    def __init__(self, access_token: Optional[str] = None, refresh_token: Optional[str] = None):
        self.creds = None
        if access_token or refresh_token:
            self.creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=None,  # Set these from config when used
                client_secret=None,
            )

    def set_credentials(self, creds: Credentials):
        self.creds = creds

    def _get_service(self):
        if not self.creds:
            raise ValueError("No credentials available. Authenticate first.")
        return build("searchconsole", "v1", credentials=self.creds)

    async def fetch_search_performance(
        self,
        days_back: int = 30,
        site_url: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch daily search performance data.

        Returns a list of dicts with: date, clicks, impressions, ctr, position
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_search_performance_sync, days_back, site_url
        )

    def _fetch_search_performance_sync(self, days_back: int, site_url: Optional[str] = None):
        url = site_url or SITE_URL
        service = self._get_service()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        request = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": ["date"],
            "rowLimit": days_back + 5,
        }

        try:
            response = service.searchanalytics().query(
                siteUrl=url, body=request
            ).execute()
        except Exception as e:
            logger.error(f"Search Console API error: {e}")
            return []

        results = []
        for row in response.get("rows", []):
            results.append({
                "date": row["keys"][0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0),
                "position": row.get("position", 0),
            })
        return results

    async def fetch_discover_performance(
        self,
        days_back: int = 30,
        site_url: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch Google Discover performance data.
        Uses Search Console API with discover filter.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_discover_performance_sync, days_back, site_url
        )

    def _fetch_discover_performance_sync(self, days_back: int, site_url: Optional[str] = None):
        url = site_url or SITE_URL
        service = self._get_service()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        request = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": ["date"],
            "dimensionFilterGroups": [{
                "filters": [{
                    "dimension": "searchAppearance",
                    "expression": "DISCOVER",
                }]
            }],
            "rowLimit": days_back + 5,
        }

        try:
            response = service.searchanalytics().query(
                siteUrl=url, body=request
            ).execute()
        except Exception as e:
            logger.error(f"Discover API error (may not be available): {e}")
            return []

        results = []
        for row in response.get("rows", []):
            results.append({
                "date": row["keys"][0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0),
            })
        return results

    async def fetch_top_queries(
        self,
        days_back: int = 7,
        limit: int = 20,
        site_url: Optional[str] = None,
    ) -> list[dict]:
        """Fetch top search queries."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_top_queries_sync, days_back, limit, site_url
        )

    def _fetch_top_queries_sync(self, days_back, limit, site_url):
        url = site_url or SITE_URL
        service = self._get_service()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        request = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": ["query"],
            "rowLimit": limit,
        }

        try:
            response = service.searchanalytics().query(
                siteUrl=url, body=request
            ).execute()
        except Exception as e:
            logger.error(f"Top queries API error: {e}")
            return []

        results = []
        for row in response.get("rows", []):
            results.append({
                "query": row["keys"][0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0),
                "position": row.get("position", 0),
            })
        return results
