"""
Analysis Engine — Genera insights, estrategias y recomendaciones accionables.

Toma los datos crudos (Threads snapshots, Search Console, Analytics)
y produce análisis comparativos, detección de tendencias, y
recomendaciones estratégicas específicas para El Espectador y VEA.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import (
    Competitor, ThreadsSnapshot, ThreadsPost,
    SearchConsoleDaily, DiscoverDaily, TrafficDaily,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Tipos de análisis
# ══════════════════════════════════════════════════════════════

class CompetitorAnalysis:
    """Resultado del análisis de un competitor."""

    def __init__(self, competitor: Competitor):
        self.competitor_name = competitor.name
        self.competitor_slug = competitor.slug
        self.is_us = competitor.is_us
        self.color = competitor.color

        # Threads metrics
        self.threads = {
            "current_followers": 0,
            "follower_growth_7d": 0.0,
            "follower_growth_30d": 0.0,
            "followers_7d_ago": 0,
            "followers_30d_ago": 0,
            "posts_count": 0,
            "avg_engagement_rate": 0.0,
            "total_snapshots": 0,
        }
        self.threads_trend = "stable"  # growing, declining, stable

        # Search metrics
        self.search = {
            "total_clicks_30d": 0,
            "total_impressions_30d": 0,
            "avg_ctr": 0.0,
            "avg_position": 0.0,
            "click_trend_7d": 0.0,
        }

        # Discover metrics
        self.discover = {
            "total_clicks_30d": 0,
            "total_impressions_30d": 0,
            "avg_ctr": 0.0,
            "click_trend_7d": 0.0,
        }

        # Traffic
        self.traffic = {
            "total_sessions_30d": 0,
            "organic_search_pct": 0.0,
            "social_pct": 0.0,
            "direct_pct": 0.0,
            "discover_pct": 0.0,
        }

        # Insights
        self.insights: list[str] = []
        self.recommendations: list[str] = []
        self.opportunities: list[str] = []
        self.risks: list[str] = []


class MarketAnalysis:
    """Análisis general del mercado y la competencia."""

    def __init__(self):
        self.total_market_followers = 0
        self.us_market_share = 0.0
        self.us_rank = 0
        self.average_growth_rate = 0.0
        self.fastest_growing: Optional[str] = None
        self.most_engaging: Optional[str] = None
        self.threads_discover_correlation = 0.0
        self.competitors: list[CompetitorAnalysis] = []
        self.overall_insights: list[str] = []
        self.overall_strategies: list[dict] = []
        self.weekly_actions: list[str] = []


# ══════════════════════════════════════════════════════════════
# Motor de análisis
# ══════════════════════════════════════════════════════════════

class AnalysisEngine:
    """
    Motor principal de análisis.

    Toma una sesión de BD con datos y produce análisis completos
    con insights, estrategias y recomendaciones.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_all(self) -> MarketAnalysis:
        """Ejecuta análisis completo de todos los competidores."""
        market = MarketAnalysis()
        competitors = (await self.db.execute(
            select(Competitor).order_by(Competitor.name)
        )).scalars().all()

        for comp in competitors:
            ca = await self._analyze_competitor(comp)
            market.competitors.append(ca)
            market.total_market_followers += ca.threads["current_followers"]

        # Calcular market share
        us_followers = sum(
            c.threads["current_followers"]
            for c in market.competitors if c.is_us
        )
        market.us_market_share = 0.0
        if market.total_market_followers > 0:
            market.us_market_share = (us_followers / market.total_market_followers) * 100

        # Ranking
        sorted_by_followers = sorted(
            market.competitors,
            key=lambda c: c.threads["current_followers"],
            reverse=True
        )
        for i, c in enumerate(sorted_by_followers):
            if c.is_us:
                market.us_rank = i + 1
            if i == 0:
                market.fastest_growing = c.competitor_name \
                    if c.threads["follower_growth_30d"] >= 0 else None

        # Más engagement
        engaging = sorted(
            market.competitors,
            key=lambda c: c.threads["avg_engagement_rate"],
            reverse=True
        )
        if engaging:
            market.most_engaging = engaging[0].competitor_name

        # Crecimiento promedio
        growth_rates = [
            c.threads["follower_growth_30d"]
            for c in market.competitors
            if c.threads["total_snapshots"] >= 2
        ]
        if growth_rates:
            market.average_growth_rate = sum(growth_rates) / len(growth_rates)

        # Generar insights generales
        market.overall_insights = self._generate_market_insights(market)
        market.overall_strategies = self._generate_strategies(market)
        market.weekly_actions = self._generate_weekly_actions(market)

        return market

    async def _analyze_competitor(self, comp: Competitor) -> CompetitorAnalysis:
        """Analiza un competidor individual."""
        ca = CompetitorAnalysis(comp)

        # ─── Threads Snapshots ──────────────────────────────
        snapshots = (await self.db.execute(
            select(ThreadsSnapshot)
            .where(ThreadsSnapshot.competitor_id == comp.id)
            .order_by(ThreadsSnapshot.snapshot_date.desc())
        )).scalars().all()

        ca.threads["total_snapshots"] = len(snapshots)

        if snapshots:
            latest = snapshots[0]
            ca.threads["current_followers"] = latest.followers
            ca.threads["posts_count"] = latest.posts_count
            ca.threads["avg_engagement_rate"] = latest.engagement_rate

            now = datetime.now(timezone.utc)

            # 7 días atrás
            snap_7d = [s for s in snapshots
                      if s.snapshot_date and s.snapshot_date >= now - timedelta(days=7)]
            if len(snap_7d) >= 2:
                ca.threads["followers_7d_ago"] = snap_7d[-1].followers
                if snap_7d[-1].followers > 0:
                    ca.threads["follower_growth_7d"] = (
                        (snap_7d[0].followers - snap_7d[-1].followers)
                        / snap_7d[-1].followers * 100
                    )

            # 30 días atrás
            snap_30d = [s for s in snapshots
                       if s.snapshot_date and s.snapshot_date >= now - timedelta(days=30)]
            if len(snap_30d) >= 2:
                ca.threads["followers_30d_ago"] = snap_30d[-1].followers
                if snap_30d[-1].followers > 0:
                    ca.threads["follower_growth_30d"] = (
                        (snap_30d[0].followers - snap_30d[-1].followers)
                        / snap_30d[-1].followers * 100
                    )

            # Tendencia
            if ca.threads["follower_growth_30d"] > 5:
                ca.threads_trend = "growing"
            elif ca.threads["follower_growth_30d"] < -2:
                ca.threads_trend = "declining"
            else:
                ca.threads_trend = "stable"

        # ─── Search Console ─────────────────────────────────
        search_data = (await self.db.execute(
            select(SearchConsoleDaily)
            .where(SearchConsoleDaily.competitor_id == comp.id)
            .order_by(SearchConsoleDaily.date.desc())
            .limit(60)
        )).scalars().all()

        if search_data:
            recent_30d = search_data[:30]
            ca.search["total_clicks_30d"] = sum(r.clicks for r in recent_30d)
            ca.search["total_impressions_30d"] = sum(r.impressions for r in recent_30d)
            if ca.search["total_impressions_30d"] > 0:
                ca.search["avg_ctr"] = (
                    ca.search["total_clicks_30d"] / ca.search["total_impressions_30d"]
                ) * 100
            if recent_30d:
                positions_with_data = [r for r in recent_30d if r.avg_position and r.avg_position > 0]
                if positions_with_data:
                    ca.search["avg_position"] = sum(
                        p.avg_position for p in positions_with_data
                    ) / len(positions_with_data)

            # Tendencia de clics 7d vs 7d anterior
            recent_7d = search_data[:7]
            prev_7d = search_data[7:14]
            if prev_7d and sum(r.clicks for r in prev_7d) > 0:
                ca.search["click_trend_7d"] = (
                    (sum(r.clicks for r in recent_7d) - sum(r.clicks for r in prev_7d))
                    / sum(r.clicks for r in prev_7d) * 100
                )

        # ─── Discover ──────────────────────────────────────
        discover_data = (await self.db.execute(
            select(DiscoverDaily)
            .where(DiscoverDaily.competitor_id == comp.id)
            .order_by(DiscoverDaily.date.desc())
            .limit(60)
        )).scalars().all()

        if discover_data:
            recent_30d = discover_data[:30]
            ca.discover["total_clicks_30d"] = sum(r.clicks for r in recent_30d)
            ca.discover["total_impressions_30d"] = sum(r.impressions for r in recent_30d)
            if ca.discover["total_impressions_30d"] > 0:
                ca.discover["avg_ctr"] = (
                    ca.discover["total_clicks_30d"] / ca.discover["total_impressions_30d"]
                ) * 100

            recent_7d = discover_data[:7]
            prev_7d = discover_data[7:14]
            if prev_7d and sum(r.clicks for r in prev_7d) > 0:
                ca.discover["click_trend_7d"] = (
                    (sum(r.clicks for r in recent_7d) - sum(r.clicks for r in prev_7d))
                    / sum(r.clicks for r in prev_7d) * 100
                )

        # ─── Traffic ───────────────────────────────────────
        traffic_data = (await self.db.execute(
            select(TrafficDaily)
            .where(TrafficDaily.competitor_id == comp.id)
            .order_by(TrafficDaily.date.desc())
            .limit(60)
        )).scalars().all()

        if traffic_data:
            recent_30d = traffic_data[:30]
            ca.traffic["total_sessions_30d"] = sum(r.sessions for r in recent_30d)
            total = ca.traffic["total_sessions_30d"]
            if total > 0:
                # Por fuente
                sources = defaultdict(int)
                for r in recent_30d:
                    sources[r.source] += r.sessions
                ca.traffic["organic_search_pct"] = (sources.get("organic_search", 0) / total) * 100
                ca.traffic["social_pct"] = (sources.get("organic_social", 0) / total) * 100
                ca.traffic["direct_pct"] = (sources.get("direct", 0) / total) * 100
                ca.traffic["discover_pct"] = (sources.get("discover", 0) / total) * 100

        # ─── Generar insights ──────────────────────────────
        ca.insights = self._generate_competitor_insights(ca)
        ca.recommendations = self._generate_recommendations(ca)
        ca.opportunities = self._generate_opportunities(ca)
        ca.risks = self._generate_risks(ca)

        return ca

    def _generate_competitor_insights(self, ca: CompetitorAnalysis) -> list[str]:
        """Genera insights específicos para un competidor."""
        insights = []

        # Crecimiento
        growth_30d = ca.threads["follower_growth_30d"]
        if growth_30d > 10:
            insights.append(
                f"📈 Crecimiento acelerado: +{growth_30d:.1f}% en Threads en 30d. "
                "Identificar qué contenido está funcionando."
            )
        elif growth_30d > 3:
            insights.append(
                f"📊 Crecimiento sostenido: +{growth_30d:.1f}% en Threads en 30d."
            )
        elif growth_30d < -3:
            insights.append(
                f"📉 Pérdida de seguidores: {growth_30d:.1f}% en 30d. "
                "Revisar cambios recientes en estrategia de contenido."
            )
        else:
            insights.append(
                f"➡️ Crecimiento estable: {growth_30d:.1f}% en Threads en 30d."
            )

        # Engagement
        if ca.threads["avg_engagement_rate"] > 0.05:
            insights.append(
                f"🔥 Alto engagement: {ca.threads['avg_engagement_rate']:.3f}%. "
                "El contenido resuena bien con la audiencia."
            )
        elif ca.threads["avg_engagement_rate"] > 0:
            insights.append(
                f"💬 Engagement moderado: {ca.threads['avg_engagement_rate']:.3f}%."
            )

        # Search performance
        if ca.search["click_trend_7d"] > 20:
            insights.append(
                f"🔍 Búsqueda en alza: +{ca.search['click_trend_7d']:.0f}% clics en 7d. "
                "Contenido bien posicionado."
            )
        elif ca.search["click_trend_7d"] < -20:
            insights.append(
                f"⚠️ Caída en búsqueda: {ca.search['click_trend_7d']:.0f}% clics en 7d. "
                "Revisar SEO on-page."
            )

        # Discover
        if ca.discover["click_trend_7d"] > 30:
            insights.append(
                f"✨ Discover trending: +{ca.discover['click_trend_7d']:.0f}% en 7d. "
                "Buen rendimiento en Google Discover."
            )

        # Traffic mix
        if ca.traffic["discover_pct"] > 30:
            insights.append(
                f"📱 Alta dependencia de Discover: {ca.traffic['discover_pct']:.0f}% del tráfico. "
                "Diversificar fuentes."
            )
        if ca.traffic["organic_search_pct"] < 20 and ca.traffic["total_sessions_30d"] > 0:
            insights.append(
                f"🔧 Oportunidad SEO: solo {ca.traffic['organic_search_pct']:.0f}% del tráfico es "
                "búsqueda orgánica. Mejorar estrategia de contenido."
            )

        return insights

    def _generate_recommendations(self, ca: CompetitorAnalysis) -> list[str]:
        """Genera recomendaciones accionables."""
        recs = []

        # Si es "nosotros", recomendaciones más específicas
        if ca.is_us:
            if ca.threads["current_followers"] < 5000:
                recs.append(
                    "🚀 Publicar 3-5 veces/día en Threads para ganar tracción inicial. "
                    "Usar hilos (threads) con contenido de valor."
                )
            elif ca.threads["current_followers"] < 50000:
                recs.append(
                    "📈 Mantener 2-3 posts/día. Interactuar respondiendo a comments. "
                    "Usar encuestas y preguntas para aumentar engagement."
                )

            if ca.threads["avg_engagement_rate"] < 0.01:
                recs.append(
                    "💡 Mejorar engagement: usar más contenido visual, preguntas abiertas, "
                    "y threads educativos. Evitar solo compartir enlaces."
                )

            if ca.discover["total_clicks_30d"] < 100:
                recs.append(
                    "🔍 Mejorar presencia en Google Discover: titulares atractivos, "
                    "imágenes de alta calidad (1200px+), contenido actual y relevante."
                )

            # Recomendación específica según tendencia
            if ca.threads_trend == "declining":
                recs.append(
                    "⚠️ Revitalizar presencia: probar nuevos formatos (video corto, "
                    "detrás de escenas, contenido exclusivo). Analizar qué perdió tracción."
                )
            elif ca.threads_trend == "growing":
                recs.append(
                    "🌟 Aprovechar momentum: duplicar estrategia de contenido que está "
                    "funcionando. Publicar en horarios pico (7-9am, 12-2pm, 7-10pm COT)."
                )
        else:
            # Recomendaciones competitivas
            if ca.threads["follower_growth_30d"] > 10:
                recs.append(
                    f"🔎 Analizar a {ca.competitor_name}: creciendo +{ca.threads['follower_growth_30d']:.0f}% en Threads. "
                    "Revisar su calendario editorial y temas populares."
                )
            if ca.threads["avg_engagement_rate"] > 0.03:
                recs.append(
                    f"📝 Estudiar engagement de {ca.competitor_name}: {ca.threads['avg_engagement_rate']:.3f}%. "
                    "Analizar tipo de contenido y tono de comunicación."
                )

        return recs

    def _generate_opportunities(self, ca: CompetitorAnalysis) -> list[str]:
        """Identifica oportunidades basadas en datos."""
        ops = []

        # Oportunidades en Threads
        if ca.threads["posts_count"] < 50 and ca.threads["current_followers"] < 1000:
            ops.append("Espacio por crecer en Threads — pocos competidores locales activos.")
        elif ca.threads["current_followers"] > 0 and ca.threads["posts_count"] == 0:
            ops.append("Perfil de Threads existe pero sin actividad — oportunidad de ganar seguidores.")

        # Oportunidades en Discover
        if ca.discover["avg_ctr"] < 3.0 and ca.discover["total_impressions_30d"] > 0:
            ops.append("Mejorar CTR de Discover optimizando titulares y metadescripciones.")
        elif ca.discover["total_impressions_30d"] == 0:
            ops.append("Google Discover no está indexando contenido. Optimizar para Discover.")

        # Oportunidades SEO
        if ca.search["avg_position"] > 15 and ca.search["total_impressions_30d"] > 0:
            ops.append("Posiciones 15+ tienen oportunidad de mejora. Enfocar SEO en palabras clave.")
        elif ca.search["avg_position"] == 0:
            ops.append("Sin datos de Search Console. Conectar API para monitoreo SEO.")

        return ops

    def _generate_risks(self, ca: CompetitorAnalysis) -> list[str]:
        """Identifica riesgos."""
        risks = []

        if not ca.threads["total_snapshots"]:
            risks.append("Sin datos de Threads — no se puede medir crecimiento.")

        if ca.threads["follower_growth_30d"] < -10:
            risks.append("Pérdida significativa de seguidores en Threads. Revisar estrategia urgente.")

        if ca.discover["click_trend_7d"] < -30:
            risks.append("Caída pronunciada en Discover. Posible penalización o cambio de algoritmo.")

        if ca.traffic["total_sessions_30d"] == 0 and ca.is_us:
            risks.append("Sin datos de tráfico web. Google Analytics no configurado.")

        return risks

    def _generate_market_insights(self, market: MarketAnalysis) -> list[str]:
        """Genera insights generales del mercado."""
        insights = []

        # Market share
        if market.us_market_share > 0:
            if market.us_market_share > 50:
                insights.append(
                    f"🏆 Dominamos el mercado de Threads con {market.us_market_share:.0f}% "
                    "de los seguidores totales monitoreados."
                )
            elif market.us_market_share > 20:
                insights.append(
                    f"🎯 Presencia sólida: {market.us_market_share:.0f}% del mercado. "
                    f"Ocupamos el puesto #{market.us_rank} en seguidores."
                )
            else:
                insights.append(
                    f"📊 Participación de {market.us_market_share:.1f}% en el mercado. "
                    f"Puesto #{market.us_rank} de {len(market.competitors)} competidores."
                )

        # Crecimiento promedio
        if market.average_growth_rate != 0:
            if market.average_growth_rate > 5:
                insights.append(
                    f"🚀 El mercado está creciendo: +{market.average_growth_rate:.1f}% "
                    "promedio en Threads. Momento de invertir."
                )
            elif market.average_growth_rate < -2:
                insights.append(
                    "⚠️ Contracción general del mercado en Threads. Diferenciarse con "
                    "contenido único."
                )

        # Tendencias
        growing_competitors = [
            c for c in market.competitors
            if c.threads["follower_growth_30d"] > 5 and not c.is_us
        ]
        if growing_competitors:
            names = [c.competitor_name for c in growing_competitors[:2]]
            insights.append(
                f"👀 Competidores en ascenso: {', '.join(names)}. "
                "Monitorear sus estrategias de contenido."
            )

        return insights

    def _generate_strategies(self, market: MarketAnalysis) -> list[dict]:
        """Genera estrategias accionables semanales/mensuales."""
        strategies = []

        # Estrategia general de contenido
        strategies.append({
            "title": "🗓️ Calendario Editorial Threads",
            "description": "Publicar contenido variado para maximizar engagement y alcance.",
            "actions": [
                "📰 40% Noticias de última hora con opinión editorial",
                "💬 25% Hilos educativos y análisis en profundidad",
                "🎬 15% Contenido multimedia (video corto, imágenes detrás de escena)",
                "📊 10% Datos y estadísticas del país",
                "🔗 10% Promoción cruzada de artículos del sitio web",
            ],
            "priority": "alta" if market.us_market_share < 30 else "media",
        })

        # Estrategia de Discover
        discover_low = any(
            c.discover["total_clicks_30d"] < 100 and c.is_us
            for c in market.competitors
        )
        strategies.append({
            "title": "🔍 Optimización Google Discover",
            "description": (
                "Google Discover premia contenido fresco, relevante y visualmente atractivo. "
                "Seguir estas prácticas para maximizar apariciones."
            ),
            "actions": [
                "🖼️ Imágenes destacadas de 1200x675px mínimo, formato WebP",
                "📰 Titulares informativos pero atractivos (60-80 caracteres)",
                "⏰ Publicar contenido entre 6am-10am para máxima ventana de indexación",
                "🏷️ Usar etiquetas HTML semánticas (h1, h2, article, time)",
                "⚡ Core Web Vitals: LCP < 2.5s, FID < 100ms, CLS < 0.1",
                "🔄 Actualizar artículos populares para mantener frescura",
            ],
            "priority": "alta" if discover_low else "media",
        })

        # Estrategia de SEO
        strategies.append({
            "title": "🔎 SEO para News Publishers",
            "description": (
                "Optimización para motores de búsqueda y Google News. "
                "Basado en mejores prácticas de E-E-A-T."
            ),
            "actions": [
                "📋 NewsArticle Schema en todos los artículos",
                "🗺️ News Sitemap actualizado cada hora",
                "✍️ Autoría visible con biografías de periodistas (E-E-A-T)",
                "🔗 Enlazar a fuentes primarias y artículos relacionados",
                "📱 Versión AMP o móvil optimizada (Core Web Vitals)",
                "🌐 URLs limpias con palabras clave del título",
            ],
            "priority": "alta",
        })

        # Estrategia de Threads+Discover sinergia
        strategies.append({
            "title": "🔄 Sinergia Threads → Discover",
            "description": (
                "Cómo usar Threads para mejorar el rendimiento en Google Discover. "
                "Threads es indexado por Google, y los hilos populares generan "
                "señales de contenido relevante."
            ),
            "actions": [
                "📣 Publicar en Threads un teaser de cada artículo importante",
                "🔗 Incluir enlace al artículo completo en el primer reply",
                "💬 Fomentar discusión (más replies = más señales a Google)",
                "⏱️ Publicar en Threads 30-60 min antes del artículo en el sitio",
                "📸 Usar la misma imagen destacada en Threads y el artículo",
                "📊 Monitorear correlación entre Threads viral y Discover spikes",
            ],
            "priority": "alta",
        })

        # Estrategia de Google News
        strategies.append({
            "title": "📰 Google News Inclusion",
            "description": (
                "Pasos para aparecer consistentemente en Google News y News Stand."
            ),
            "actions": [
                "✅ Registrar en Google Publisher Center",
                "📋 Enviar News Sitemap a Google Search Console",
                "🏷️ Usar NewsArticle schema con headline, datePublished, dateModified",
                "🎯 Enfocar en contenido original, no sindicado",
                "⏰ Publicar breaking news con rapidez y precisión",
            ],
            "priority": "alta",
        })

        return strategies

    def _generate_weekly_actions(self, market: MarketAnalysis) -> list[str]:
        """Genera una lista de acciones semanales prioritarias."""
        actions = []

        # Acciones basadas en el estado actual
        no_data = any(
            not c.threads["total_snapshots"] and c.is_us
            for c in market.competitors
        )
        if no_data:
            actions.append("🔴 PRIORIDAD: Configurar scraping de Threads para El Espectador y VEA")

        no_search = any(
            c.search["total_clicks_30d"] == 0 and c.is_us
            for c in market.competitors
        )
        if no_search:
            actions.append("🟡 PRIORIDAD: Conectar Google Search Console via OAuth")

        actions.append("📊 Tomar snapshot diario de Threads de todos los competidores")

        slow_growth = any(
            c.threads["follower_growth_30d"] < 2 and c.is_us
            for c in market.competitors
        )
        if slow_growth:
            actions.append("📝 Revisar estrategia de contenido en Threads — crecimiento lento")

        competitors_growing = [
            c for c in market.competitors
            if c.threads["follower_growth_30d"] > 10 and not c.is_us
        ]
        if competitors_growing:
            for c in competitors_growing[:2]:
                actions.append(f"🔎 Analizar últimas publicaciones de {c.competitor_name} en Threads")

        actions.append("📈 Revisar dashboard diariamente para detectar anomalías")
        actions.append("🔄 Publicar al menos 3 threads originales")

        return actions
