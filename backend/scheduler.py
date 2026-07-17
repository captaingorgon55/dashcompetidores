"""
Background Scheduler — Recolección automática de datos.

Ejecuta tareas periódicas:
- Cada hora: scrapea Threads de todos los competidores
- Cada 6 horas: intenta sincronizar con Google APIs (si hay tokens)
- Cada 24 horas: genera análisis completo y limpia datos viejos

Usa APScheduler para ejecución en segundo plano.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from backend.database import (
    async_session_factory, Competitor, ThreadsSnapshot,
    GoogleToken,
)
from backend.scrapers.threads import scrape_threads_profile
from backend.analysis.engine import AnalysisEngine

logger = logging.getLogger(__name__)

# Variable global para el scheduler
scheduler = None


async def scrape_all_threads():
    """
    Scrapea Threads de TODOS los competidores registrados.
    Se ejecuta cada hora.
    """
    logger.info("🔄 Iniciando scrapeo programado de Threads...")
    async with async_session_factory() as session:
        competitors = (await session.execute(
            select(Competitor)
        )).scalars().all()

        results = []
        for comp in competitors:
            if not comp.threads_handle:
                logger.debug(f"  ⏭️ {comp.name}: sin handle de Threads")
                continue

            try:
                data = await scrape_threads_profile(comp.threads_handle)
                if data:
                    snapshot = ThreadsSnapshot(
                        competitor_id=comp.id,
                        followers=data.get("followers", 0),
                        following=data.get("following", 0),
                        posts_count=data.get("posts", 0),
                        snapshot_date=datetime.utcnow(),
                        raw_data=data,
                    )
                    session.add(snapshot)
                    results.append({
                        "name": comp.name,
                        "followers": data.get("followers", 0),
                        "status": "ok",
                    })
                    logger.info(f"  ✅ {comp.name}: {data.get('followers', 0)} seguidores")
                else:
                    logger.warning(f"  ⚠️ {comp.name}: sin datos")
                    results.append({"name": comp.name, "followers": 0, "status": "error"})
            except Exception as e:
                logger.error(f"  ❌ {comp.name}: {e}")
                results.append({"name": comp.name, "followers": 0, "status": "error"})

        await session.commit()

        total = sum(r["followers"] for r in results if r["status"] == "ok")
        ok_count = sum(1 for r in results if r["status"] == "ok")
        logger.info(f"✅ Scrapeo completado: {ok_count}/{len(results)} perfiles ok, "
                     f"{total} seguidores totales")


async def generate_analysis_report():
    """
    Genera un reporte de análisis completo con los datos actuales.
    Se ejecuta cada 24 horas.
    """
    logger.info("📊 Generando reporte de análisis diario...")
    async with async_session_factory() as session:
        engine = AnalysisEngine(session)
        market = await engine.analyze_all()

        if market.overall_insights:
            for insight in market.overall_insights[:3]:
                logger.info(f"  💡 {insight}")

        if market.overall_strategies:
            for strategy in market.overall_strategies[:2]:
                logger.info(f"  📋 {strategy['title']}")

        logger.info(f"✅ Análisis completado: {len(market.competitors)} competidores analizados")
        return market


async def check_google_connection():
    """
    Verifica la conexión con Google APIs y refresca tokens si es necesario.
    Se ejecuta cada 6 horas.
    """
    async with async_session_factory() as session:
        token = (await session.execute(select(GoogleToken))).scalar_one_or_none()
        if not token:
            logger.info("⏭️ Google APIs: no hay tokens configurados")
            return

        now = datetime.now(timezone.utc).timestamp()
        if now >= token.expires_at:
            # Intentar refresh
            from backend.auth import get_google_credentials
            creds = await get_google_credentials()
            if creds:
                logger.info("✅ Google token refrescado exitosamente")
            else:
                logger.warning("⚠️ No se pudo refrescar token de Google")
        else:
            logger.info(f"✅ Google token válido hasta "
                        f"{datetime.fromtimestamp(token.expires_at, tz=timezone.utc)}")


# ─── Inicialización ──────────────────────────────────────────────

def init_scheduler():
    """
    Inicializa el scheduler con las tareas periódicas.
    Se llama al iniciar la aplicación.
    """
    global scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        # Scrapeo de Threads cada hora
        scheduler.add_job(
            scrape_all_threads,
            IntervalTrigger(hours=1),
            id="scrape_threads_hourly",
            name="Scrapear Threads cada hora",
            replace_existing=True,
        )

        # Verificar Google conexión cada 6 horas
        scheduler.add_job(
            check_google_connection,
            IntervalTrigger(hours=6),
            id="check_google_6h",
            name="Verificar Google APIs cada 6h",
            replace_existing=True,
        )

        # Análisis completo cada 24 horas
        scheduler.add_job(
            generate_analysis_report,
            IntervalTrigger(hours=24),
            id="analysis_daily",
            name="Análisis completo diario",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("✅ Scheduler iniciado con tareas periódicas")

        # Ejecutar primer scrapeo inmediatamente
        import asyncio
        asyncio.create_task(scrape_all_threads())
        logger.info("🔄 Primer scrapeo automático iniciado")

    except ImportError:
        logger.warning("⚠️ APScheduler no instalado. Tareas automáticas deshabilitadas.")
    except Exception as e:
        logger.error(f"❌ Error iniciando scheduler: {e}")
