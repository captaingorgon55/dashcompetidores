"""
Competitor Dashboard — Main FastAPI Application

Live competitor analysis dashboard for news media.
Tracks Threads metrics, Google Search Console, Google Analytics,
and generates AI-powered analysis and strategy recommendations.
"""

import logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.database import (
    init_db, seed_default_competitors, get_session,
    Competitor, ThreadsSnapshot, ThreadsPost,
    SearchConsoleDaily, DiscoverDaily, TrafficDaily, ManualEntry,
)
from backend.scrapers.threads import scrape_threads_profile, scrape_threads_posts
from backend.auth import router as auth_router, get_google_credentials
from backend.analysis.engine import AnalysisEngine
from backend.scheduler import init_scheduler as init_bg_scheduler
from backend.config import DEFAULT_COMPETITORS, FRONTEND_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Lifecycle ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_default_competitors()
    # Iniciar scheduler de tareas automáticas
    try:
        init_bg_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler no iniciado: {e}")
    yield


app = FastAPI(
    title="Competitor Dashboard — El Espectador & Revista VEA",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(auth_router)

# Servir frontend
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


# ─── Health Check ────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "threads_scraper": True,
            "analysis_engine": True,
            "google_oauth": True,
            "auto_scheduler": True,
        },
    }


# ══════════════════════════════════════════════════════════════
# Pydantic Schemas
# ══════════════════════════════════════════════════════════════

class CompetitorOut(BaseModel):
    id: int
    slug: str
    name: str
    threads_handle: str | None = None
    threads_url: str | None = None
    site_url: str | None = None
    color: str | None = None
    is_us: bool = False
    notes: str | None = None

    class Config:
        from_attributes = True


class ThreadsSnapshotOut(BaseModel):
    id: int
    competitor_id: int
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    engagement_rate: float = 0.0
    avg_likes: float = 0.0
    avg_replies: float = 0.0
    snapshot_date: datetime | None = None

    class Config:
        from_attributes = True


class ManualEntryCreate(BaseModel):
    competitor_id: int
    category: str
    metric_name: str
    metric_value: float | None = None
    metric_text: str | None = None
    entry_date: str
    notes: str | None = None


class ManualEntryOut(BaseModel):
    id: int
    competitor_id: int
    category: str
    metric_name: str
    metric_value: float | None = None
    metric_text: str | None = None
    entry_date: datetime | None = None
    notes: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# Helper: Serve frontend HTML
# ══════════════════════════════════════════════════════════════

async def serve_html(filename: str):
    path = FRONTEND_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Page not found")
    content = path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


# ══════════════════════════════════════════════════════════════
# Routes — Frontend Pages
# ══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index():
    return await serve_html("dashboard.html")


@app.get("/competitors", response_class=HTMLResponse)
async def competitors_page():
    return await serve_html("competitors.html")


@app.get("/threads", response_class=HTMLResponse)
async def threads_page():
    return await serve_html("threads.html")


@app.get("/discover", response_class=HTMLResponse)
async def discover_page():
    return await serve_html("discover.html")


@app.get("/search", response_class=HTMLResponse)
async def search_page():
    return await serve_html("search.html")


@app.get("/manual-entry", response_class=HTMLResponse)
async def manual_entry_page():
    return await serve_html("manual-entry.html")


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page():
    return await serve_html("analysis.html")


# ══════════════════════════════════════════════════════════════
# API Routes — Competitors
# ══════════════════════════════════════════════════════════════

@app.get("/api/competitors", response_model=list[CompetitorOut])
async def list_competitors(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Competitor).order_by(Competitor.name))
    return result.scalars().all()


@app.get("/api/competitors/{competitor_id}", response_model=CompetitorOut)
async def get_competitor(competitor_id: int, db: AsyncSession = Depends(get_session)):
    comp = await db.get(Competitor, competitor_id)
    if not comp:
        raise HTTPException(404, "Competitor not found")
    return comp


@app.post("/api/competitors", response_model=CompetitorOut)
async def create_competitor(
    name: str,
    threads_handle: str = "",
    site_url: str = "",
    is_us: bool = False,
    db: AsyncSession = Depends(get_session),
):
    """Crear un nuevo competidor para monitorear."""
    import re
    slug = re.sub(r'[^a-z0-9]', '_', name.lower().strip())[:50]
    if not slug:
        raise HTTPException(400, "Invalid name")

    comp = Competitor(
        slug=slug,
        name=name,
        threads_handle=threads_handle,
        threads_url=f"https://www.threads.net/{threads_handle}" if threads_handle else None,
        site_url=site_url,
        is_us=is_us,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


# ══════════════════════════════════════════════════════════════
# API Routes — Threads
# ══════════════════════════════════════════════════════════════

@app.post("/api/threads/scrape/{competitor_id}")
async def scrape_competitor_threads(
    competitor_id: int,
    include_posts: bool = Query(False, description="Incluir posts recientes"),
    db: AsyncSession = Depends(get_session),
):
    """Scrapea datos reales de Threads de un competidor."""
    comp = await db.get(Competitor, competitor_id)
    if not comp:
        raise HTTPException(404, "Competitor not found")
    if not comp.threads_handle:
        raise HTTPException(400, "Competitor has no Threads handle")

    # Scrapear perfil
    data = await scrape_threads_profile(comp.threads_handle)
    if not data:
        raise HTTPException(502, "No se pudo obtener datos de Threads")

    # Calcular engagement rate (likes+replies por post / followers)
    followers = data.get("followers", 0)
    engagement_rate = 0.0
    if followers > 0 and data.get("posts", 0) > 0:
        # Estimación: si tenemos posts de la respuesta
        pass

    snapshot = ThreadsSnapshot(
        competitor_id=competitor_id,
        followers=followers,
        following=data.get("following", 0),
        posts_count=data.get("posts", 0),
        engagement_rate=engagement_rate,
        snapshot_date=datetime.now(timezone.utc),
        raw_data=data,
    )
    db.add(snapshot)

    # Scrapear posts si se solicita
    posts_scraped = 0
    if include_posts and followers > 0:
        try:
            posts = await scrape_threads_posts(comp.threads_handle, limit=10)
            for p in posts:
                post = ThreadsPost(
                    competitor_id=competitor_id,
                    post_id=p.get("post_id"),
                    text=p.get("text", ""),
                    likes=p.get("likes", 0),
                    replies=p.get("replies", 0),
                    reposts=p.get("reposts", 0),
                    has_image=p.get("has_image", False),
                    has_video=p.get("has_video", False),
                    posted_at=datetime.fromtimestamp(p["taken_at"], tz=timezone.utc)
                    if p.get("taken_at") else None,
                )
                db.add(post)
                posts_scraped += 1
        except Exception as e:
            logger.warning(f"Error scrapeando posts de {comp.threads_handle}: {e}")

    await db.commit()
    await db.refresh(snapshot)

    return {
        "status": "ok",
        "snapshot_id": snapshot.id,
        "data": data,
        "posts_scraped": posts_scraped,
    }


@app.post("/api/threads/scrape-all")
async def scrape_all_threads(
    db: AsyncSession = Depends(get_session),
):
    """Scrapea Threads de todos los competidores a la vez."""
    competitors = (await db.execute(select(Competitor))).scalars().all()
    results = []

    for comp in competitors:
        if not comp.threads_handle:
            continue
        try:
            data = await scrape_threads_profile(comp.threads_handle)
            if data:
                snapshot = ThreadsSnapshot(
                    competitor_id=comp.id,
                    followers=data.get("followers", 0),
                    following=data.get("following", 0),
                    posts_count=data.get("posts", 0),
                    snapshot_date=datetime.now(timezone.utc),
                    raw_data=data,
                )
                db.add(snapshot)
                results.append({
                    "name": comp.name,
                    "followers": data.get("followers", 0),
                    "status": "ok",
                })
            else:
                results.append({"name": comp.name, "followers": 0, "status": "error"})
        except Exception as e:
            logger.error(f"Error scrapeando {comp.name}: {e}")
            results.append({"name": comp.name, "followers": 0, "status": "error"})

    await db.commit()

    return {
        "status": "ok",
        "results": results,
        "total_followers": sum(r["followers"] for r in results if r["status"] == "ok"),
        "successful": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] == "error"),
    }


@app.get("/api/threads/snapshots/{competitor_id}")
async def get_threads_snapshots(
    competitor_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    """Historical Threads snapshots."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(ThreadsSnapshot)
        .where(ThreadsSnapshot.competitor_id == competitor_id)
        .where(ThreadsSnapshot.snapshot_date >= cutoff)
        .order_by(ThreadsSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()
    return [
        {
            "id": s.id,
            "followers": s.followers,
            "following": s.following,
            "posts_count": s.posts_count,
            "engagement_rate": s.engagement_rate,
            "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
        }
        for s in snapshots
    ]


@app.get("/api/threads/latest-all")
async def get_all_latest_threads(db: AsyncSession = Depends(get_session)):
    """Latest Threads snapshot for ALL competitors."""
    competitors = (await db.execute(select(Competitor))).scalars().all()
    results = []
    for comp in competitors:
        result = await db.execute(
            select(ThreadsSnapshot)
            .where(ThreadsSnapshot.competitor_id == comp.id)
            .order_by(ThreadsSnapshot.snapshot_date.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        results.append({
            "competitor": {
                "id": comp.id,
                "name": comp.name,
                "slug": comp.slug,
                "color": comp.color,
                "is_us": comp.is_us,
                "threads_handle": comp.threads_handle,
            },
            "snapshot": {
                "followers": latest.followers if latest else 0,
                "following": latest.following if latest else 0,
                "posts_count": latest.posts_count if latest else 0,
                "engagement_rate": latest.engagement_rate if latest else 0,
                "snapshot_date": latest.snapshot_date.isoformat() if latest else None,
                "needs_update": not latest or (
                    datetime.now(timezone.utc) - latest.snapshot_date
                ).total_seconds() > 3600,
            } if latest else None,
        })
    return results


@app.get("/api/threads/posts/{competitor_id}")
async def get_threads_posts(
    competitor_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
):
    """Get scraped posts for a competitor."""
    result = await db.execute(
        select(ThreadsPost)
        .where(ThreadsPost.competitor_id == competitor_id)
        .order_by(ThreadsPost.scraped_at.desc())
        .limit(limit)
    )
    posts = result.scalars().all()
    return [
        {
            "id": p.id,
            "post_id": p.post_id,
            "text": p.text[:200] if p.text else "",
            "likes": p.likes,
            "replies": p.replies,
            "reposts": p.reposts,
            "has_image": p.has_image,
            "has_video": p.has_video,
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
        }
        for p in posts
    ]


# ══════════════════════════════════════════════════════════════
# API Routes — Discover & Search Console
# ══════════════════════════════════════════════════════════════

@app.get("/api/discover/{competitor_id}")
async def get_discover_data(
    competitor_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    """Get Google Discover performance data."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(DiscoverDaily)
        .where(DiscoverDaily.competitor_id == competitor_id)
        .where(DiscoverDaily.date >= cutoff)
        .order_by(DiscoverDaily.date)
    )
    records = result.scalars().all()
    return [
        {
            "date": r.date.isoformat(),
            "impressions": r.impressions,
            "clicks": r.clicks,
            "ctr": r.ctr,
        }
        for r in records
    ]


@app.get("/api/search/{competitor_id}")
async def get_search_data(
    competitor_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    """Get Google Search performance data."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(SearchConsoleDaily)
        .where(SearchConsoleDaily.competitor_id == competitor_id)
        .where(SearchConsoleDaily.date >= cutoff)
        .order_by(SearchConsoleDaily.date)
    )
    records = result.scalars().all()
    return [
        {
            "date": r.date.isoformat(),
            "clicks": r.clicks,
            "impressions": r.impressions,
            "ctr": r.ctr,
            "avg_position": r.avg_position,
        }
        for r in records
    ]


# ══════════════════════════════════════════════════════════════
# API Routes — Manual Entries
# ══════════════════════════════════════════════════════════════

@app.post("/api/manual-entries", response_model=ManualEntryOut)
async def create_manual_entry(
    entry: ManualEntryCreate,
    db: AsyncSession = Depends(get_session),
):
    """Create a manual data entry."""
    comp = await db.get(Competitor, entry.competitor_id)
    if not comp:
        raise HTTPException(404, "Competitor not found")

    try:
        entry_date = datetime.strptime(entry.entry_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    db_entry = ManualEntry(
        competitor_id=entry.competitor_id,
        category=entry.category,
        metric_name=entry.metric_name,
        metric_value=entry.metric_value,
        metric_text=entry.metric_text,
        entry_date=entry_date,
        notes=entry.notes,
    )
    db.add(db_entry)
    await db.commit()
    await db.refresh(db_entry)
    return db_entry


@app.get("/api/manual-entries")
async def get_manual_entries(
    competitor_id: int | None = Query(None),
    category: str | None = Query(None),
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    """Get manual entries with optional filters."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(ManualEntry).where(ManualEntry.entry_date >= cutoff)

    if competitor_id:
        query = query.where(ManualEntry.competitor_id == competitor_id)
    if category:
        query = query.where(ManualEntry.category == category)

    query = query.order_by(ManualEntry.entry_date.desc())
    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "competitor_id": e.competitor_id,
            "category": e.category,
            "metric_name": e.metric_name,
            "metric_value": e.metric_value,
            "metric_text": e.metric_text,
            "entry_date": e.entry_date.isoformat() if e.entry_date else None,
            "notes": e.notes,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


# ══════════════════════════════════════════════════════════════
# ⚡ ANALYSIS ENGINE ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.get("/api/analysis/market")
async def get_market_analysis(db: AsyncSession = Depends(get_session)):
    """
    Análisis completo del mercado: insights, estrategias y acciones.
    Es el endpoint principal del Analysis Engine.
    """
    engine = AnalysisEngine(db)
    market = await engine.analyze_all()

    return {
        "market": {
            "total_followers": market.total_market_followers,
            "us_market_share": round(market.us_market_share, 1),
            "us_rank": market.us_rank,
            "average_growth_rate": round(market.average_growth_rate, 2),
            "fastest_growing": market.fastest_growing,
            "most_engaging": market.most_engaging,
        },
        "competitors": [
            {
                "name": c.competitor_name,
                "slug": c.competitor_slug,
                "is_us": c.is_us,
                "color": c.color,
                "threads": c.threads,
                "threads_trend": c.threads_trend,
                "search": c.search,
                "discover": c.discover,
                "traffic": c.traffic,
                "insights": c.insights,
                "recommendations": c.recommendations,
                "opportunities": c.opportunities,
                "risks": c.risks,
            }
            for c in market.competitors
        ],
        "overall_insights": market.overall_insights,
        "overall_strategies": market.overall_strategies,
        "weekly_actions": market.weekly_actions,
    }


@app.get("/api/analysis/competitor/{competitor_id}")
async def get_competitor_analysis(
    competitor_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    Análisis detallado de un competidor específico.
    """
    comp = await db.get(Competitor, competitor_id)
    if not comp:
        raise HTTPException(404, "Competitor not found")

    engine = AnalysisEngine(db)
    market = await engine.analyze_all()

    for c in market.competitors:
        if c.competitor_slug == comp.slug:
            return {
                "competitor": {
                    "name": c.competitor_name,
                    "slug": c.competitor_slug,
                    "is_us": c.is_us,
                    "color": c.color,
                },
                "threads": c.threads,
                "threads_trend": c.threads_trend,
                "search": c.search,
                "discover": c.discover,
                "traffic": c.traffic,
                "insights": c.insights,
                "recommendations": c.recommendations,
                "opportunities": c.opportunities,
                "risks": c.risks,
            }

    raise HTTPException(404, "Analysis not available yet. Scrape some data first.")


@app.get("/api/analysis/strategies")
async def get_strategies(db: AsyncSession = Depends(get_session)):
    """Solo las estrategias de contenido."""
    engine = AnalysisEngine(db)
    market = await engine.analyze_all()
    return {
        "strategies": market.overall_strategies,
        "weekly_actions": market.weekly_actions,
    }


@app.get("/api/analysis/insights")
async def get_insights(db: AsyncSession = Depends(get_session)):
    """Solo insights y oportunidades."""
    engine = AnalysisEngine(db)
    market = await engine.analyze_all()

    all_insights = []
    all_opportunities = []
    all_risks = []

    for c in market.competitors:
        for insight in c.insights:
            all_insights.append({
                "competitor": c.competitor_name,
                "is_us": c.is_us,
                "insight": insight,
            })
        for opp in c.opportunities:
            all_opportunities.append({
                "competitor": c.competitor_name,
                "is_us": c.is_us,
                "opportunity": opp,
            })

    return {
        "overall_insights": market.overall_insights,
        "competitor_insights": all_insights,
        "opportunities": all_opportunities,
    }


# ══════════════════════════════════════════════════════════════
# API Routes — Dashboard Summary
# ══════════════════════════════════════════════════════════════

@app.get("/api/dashboard/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_session)):
    """Aggregated summary for the main dashboard."""
    competitors = (await db.execute(select(Competitor))).scalars().all()

    summary = []
    for comp in competitors:
        # Latest Threads snapshot
        ts_result = await db.execute(
            select(ThreadsSnapshot)
            .where(ThreadsSnapshot.competitor_id == comp.id)
            .order_by(ThreadsSnapshot.snapshot_date.desc())
            .limit(1)
        )
        ts = ts_result.scalar_one_or_none()

        # Compare with previous snapshot for growth
        ts_prev_result = await db.execute(
            select(ThreadsSnapshot)
            .where(ThreadsSnapshot.competitor_id == comp.id)
            .order_by(ThreadsSnapshot.snapshot_date.desc())
            .offset(1).limit(1)
        )
        ts_prev = ts_prev_result.scalar_one_or_none()

        follower_growth = 0
        if ts and ts_prev and ts_prev.followers > 0:
            follower_growth = ((ts.followers - ts_prev.followers) / ts_prev.followers) * 100

        # Latest 7 days traffic
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        traffic_result = await db.execute(
            select(func.sum(TrafficDaily.sessions))
            .where(TrafficDaily.competitor_id == comp.id)
            .where(TrafficDaily.date >= week_ago)
        )
        weekly_sessions = traffic_result.scalar() or 0

        # Latest 7 days discover
        discover_result = await db.execute(
            select(func.sum(DiscoverDaily.clicks))
            .where(DiscoverDaily.competitor_id == comp.id)
            .where(DiscoverDaily.date >= week_ago)
        )
        weekly_discover_clicks = discover_result.scalar() or 0

        # Trend indicator
        trend = "stable"
        if follower_growth > 5:
            trend = "growing"
        elif follower_growth < -2:
            trend = "declining"

        summary.append({
            "competitor_id": comp.id,
            "name": comp.name,
            "slug": comp.slug,
            "color": comp.color,
            "is_us": comp.is_us,
            "threads_followers": ts.followers if ts else 0,
            "threads_follower_growth": round(follower_growth, 2),
            "threads_trend": trend,
            "threads_engagement": ts.engagement_rate if ts else 0,
            "weekly_sessions": weekly_sessions,
            "weekly_discover_clicks": weekly_discover_clicks,
            "last_updated": ts.snapshot_date.isoformat() if ts else None,
        })

    return {"competitors": summary}


# ─── Run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
