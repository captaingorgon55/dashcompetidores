"""
Database models for the Competitor Dashboard.
SQLite + SQLAlchemy async.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.config import DB_PATH

Base = declarative_base()


# ══════════════════════════════════════════════════════════════
# Competitors
# ══════════════════════════════════════════════════════════════

class Competitor(Base):
    """A media outlet we're tracking (us or competitor)."""
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    threads_handle = Column(String(100))
    threads_url = Column(String(500))
    site_url = Column(String(500))
    color = Column(String(7), default="#3B82F6")
    is_us = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════
# Threads Metrics
# ══════════════════════════════════════════════════════════════

class ThreadsSnapshot(Base):
    """A snapshot of a competitor's Threads profile metrics."""
    __tablename__ = "threads_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    followers = Column(Integer, default=0)
    following = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)  # avg likes+replies per post / followers
    avg_likes = Column(Float, default=0.0)
    avg_replies = Column(Float, default=0.0)
    top_post_text = Column(Text)
    top_post_likes = Column(Integer, default=0)
    top_post_replies = Column(Integer, default=0)
    snapshot_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    raw_data = Column(JSON)  # full scrape dump


class ThreadsPost(Base):
    """Individual post data from a competitor's Threads feed."""
    __tablename__ = "threads_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    post_id = Column(String(100), unique=True)
    text = Column(Text)
    likes = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    reposts = Column(Integer, default=0)
    has_image = Column(Boolean, default=False)
    has_video = Column(Boolean, default=False)
    posted_at = Column(DateTime)
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════
# Google Search Console Data
# ══════════════════════════════════════════════════════════════

class SearchConsoleDaily(Base):
    """Daily search performance data from Google Search Console."""
    __tablename__ = "search_console_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    clicks = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    avg_position = Column(Float, default=0.0)
    query = Column(String(500))  # null = total, otherwise breakdown
    source = Column(String(50), default="google")  # google, bing


class DiscoverDaily(Base):
    """Daily Google Discover performance data."""
    __tablename__ = "discover_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)


# ══════════════════════════════════════════════════════════════
# Google Analytics Traffic
# ══════════════════════════════════════════════════════════════

class TrafficDaily(Base):
    """Daily traffic data broken down by source."""
    __tablename__ = "traffic_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    source = Column(String(50), nullable=False)  # direct, organic_social, organic_search, referral, discover
    sessions = Column(Integer, default=0)
    pageviews = Column(Integer, default=0)
    avg_session_duration = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)


# ══════════════════════════════════════════════════════════════
# Manual Entries
# ══════════════════════════════════════════════════════════════

class ManualEntry(Base):
    """User-entered data points for things we can't automate."""
    __tablename__ = "manual_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competitor_id = Column(Integer, nullable=False, index=True)
    category = Column(String(50), nullable=False)  # threads, discover, search, traffic, notes
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float)
    metric_text = Column(Text)
    entry_date = Column(DateTime, nullable=False, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════
# Google OAuth Tokens
# ══════════════════════════════════════════════════════════════

class GoogleToken(Base):
    """Almacena tokens de Google OAuth2."""
    __tablename__ = "google_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, default="")
    expires_at = Column(Float, nullable=False)  # timestamp UTC
    scope = Column(Text, default="")
    token_type = Column(String(50), default="Bearer")
    user_email = Column(String(200), default="")
    user_name = Column(String(200), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════
# Engine & Session
# ══════════════════════════════════════════════════════════════

# Ensure data directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """Get an async database session."""
    async with async_session_factory() as session:
        yield session


async def seed_default_competitors():
    """Insert default competitors if table is empty."""
    from sqlalchemy import select, func
    from backend.config import DEFAULT_COMPETITORS

    async with async_session_factory() as session:
        count = await session.scalar(select(func.count(Competitor.id)))
        if count and count > 0:
            return
        for slug, data in DEFAULT_COMPETITORS.items():
            comp = Competitor(
                slug=slug,
                name=data["name"],
                threads_handle=data["threads_handle"],
                threads_url=data["threads_url"],
                site_url=data["site_url"],
                color=data["color"],
                is_us=data["is_us"],
            )
            session.add(comp)
        await session.commit()
