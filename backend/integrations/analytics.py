"""
Google Analytics Data API v1 integration.

Fetches traffic data broken down by source/medium.
Requires OAuth2 credentials configured in environment.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)

logger = logging.getLogger(__name__)


class AnalyticsClient:
    """Client for Google Analytics Data API."""

    def __init__(self, property_id: Optional[str] = None):
        self.property_id = property_id
        self.creds = None

    def set_credentials(self, creds: Credentials):
        self.creds = creds

    def _get_client(self):
        if not self.creds:
            raise ValueError("No credentials available. Authenticate first.")
        return BetaAnalyticsDataClient(credentials=self.creds)

    async def fetch_traffic_by_source(
        self,
        days_back: int = 30,
        property_id: Optional[str] = None,
    ) -> list[dict]:
        """Fetch sessions/pageviews by source/medium for the last N days."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_traffic_by_source_sync, days_back, property_id
        )

    def _fetch_traffic_by_source_sync(self, days_back, property_id):
        pid = property_id or self.property_id
        if not pid:
            logger.error("No GA4 property ID configured")
            return []

        client = self._get_client()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        request = RunReportRequest(
            property=f"properties/{pid}",
            dimensions=[
                Dimension(name="date"),
                Dimension(name="sessionDefaultChannelGroup"),
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="screenPageViews"),
                Metric(name="averageSessionDuration"),
                Metric(name="bounceRate"),
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )],
            limit=days_back * 10,
        )

        try:
            response = client.run_report(request)
        except Exception as e:
            logger.error(f"Analytics API error: {e}")
            return []

        results = []
        for row in response.rows:
            results.append({
                "date": row.dimension_values[0].value,
                "source": row.dimension_values[1].value,
                "sessions": int(row.metric_values[0].value or 0),
                "users": int(row.metric_values[1].value or 0),
                "pageviews": int(row.metric_values[2].value or 0),
                "avg_session_duration": float(row.metric_values[3].value or 0),
                "bounce_rate": float(row.metric_values[4].value or 0),
            })
        return results

    async def fetch_traffic_daily(
        self,
        days_back: int = 30,
        property_id: Optional[str] = None,
    ) -> list[dict]:
        """Fetch daily total traffic."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_traffic_daily_sync, days_back, property_id
        )

    def _fetch_traffic_daily_sync(self, days_back, property_id):
        pid = property_id or self.property_id
        if not pid:
            return []

        client = self._get_client()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        request = RunReportRequest(
            property=f"properties/{pid}",
            dimensions=[Dimension(name="date")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="screenPageViews"),
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )],
            limit=days_back + 5,
        )

        try:
            response = client.run_report(request)
        except Exception as e:
            logger.error(f"Analytics daily API error: {e}")
            return []

        results = []
        for row in response.rows:
            results.append({
                "date": row.dimension_values[0].value,
                "sessions": int(row.metric_values[0].value or 0),
                "users": int(row.metric_values[1].value or 0),
                "pageviews": int(row.metric_values[2].value or 0),
            })
        return results
