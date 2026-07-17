"""
Threads Scraper v4 — Simplificado — Playwright como estrategia principal.

Estrategias:
  1. Meta Graph API (Oficial — requiere META_ACCESS_TOKEN + app aprobada)
  2. Playwright Headless (PRINCIPAL ✅ — navegador real con anti-detección)
  3. LLM Scraper (Fallback IA — requiere GROQ_API_KEY)

threads.com NO sirve datos a httpx (redirige a login).
Playwright (o Meta API) son las únicas estrategias que funcionan.
"""

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.config import (
    MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    META_ACCESS_TOKEN, PLAYWRIGHT_TIMEOUT_MS,
    LLM_PROVIDER, LLM_SCRAPER_TIMEOUT,
)
from backend.scrapers.llm_scraper_bridge import llm_scrape_profile, llm_scrape_posts

# Playwright es obligatorio para este scraper.
# Si no está instalado, el scraper solo podrá usar Meta API.
PLAYWRIGHT_AVAILABLE = False
playwright_manager = None
try:
    from backend.scrapers.playwright_manager import playwright_manager
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.info("ℹ️ Playwright no disponible — solo Meta API disponible")

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Utilidades
# ══════════════════════════════════════════════════════════════

async def _a_jitter_delay(base_min: float = None, base_max: float = None):
    """Pausa async con jitter aleatorio."""
    min_d = base_min or MIN_DELAY_BETWEEN_REQUESTS
    max_d = base_max or MAX_DELAY_BETWEEN_REQUESTS
    await asyncio.sleep(random.uniform(min_d, max_d))


def _extract_from_hidden_json(html: str) -> Optional[dict]:
    """
    Extrae datos de los <script type="application/json" data-sjs>.
    Threads embebe datos completos del perfil en estos scripts.
    """
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/json")
    combined = {}
    for script in scripts:
        if not script.string:
            continue
        if script.get("data-sjs") is None and not any(
            key in (script.string[:500]) for key in ["user", "thread", "follower"]
        ):
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                combined.update(data)
        except (json.JSONDecodeError, AttributeError):
            continue
    return combined if combined else None


def _deep_find(obj, target_keys: set, max_depth: int = 20, _depth: int = 0):
    """Búsqueda recursiva en JSON. Retorna el primer dict con TODOS los target_keys."""
    if _depth > max_depth:
        return None
    if isinstance(obj, dict):
        if target_keys.issubset(obj.keys()) and any(obj.get(k) for k in target_keys):
            return obj
        for v in obj.values():
            result = _deep_find(v, target_keys, max_depth, _depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_find(item, target_keys, max_depth, _depth + 1)
            if result:
                return result
    return None


# ══════════════════════════════════════════════════════════════
# ThreadsScraperPremium v4
# ══════════════════════════════════════════════════════════════

class ThreadsScraperPremium:
    """
    Scraper premium de Threads — Playwright como motor principal.

    Solo usa estrategias que realmente funcionan contra threads.com:
    - Meta Graph API (oficial)
    - Playwright Headless (principal)
    - LLM Scraper (fallback con IA)
    """

    BASE_URL = "https://www.threads.com"
    META_GRAPH_API = "https://graph.threads.net"
    META_API_VERSION = "v21.0"

    async def scrape_profile(self, handle: str) -> Optional[dict]:
        """Scrapea perfil usando cadena de estrategias."""
        clean_handle = handle.lstrip("@")
        logger.info(f"🔍 Scrapeando perfil @{clean_handle}...")

        # ─── Estrategia 1: Meta Graph API ─────────────────────
        if META_ACCESS_TOKEN:
            try:
                data = await self._meta_graph_api_profile(clean_handle)
                if data:
                    logger.info(f"✅ Meta API: @{clean_handle} — {data['followers']} seguidores")
                    return data
            except Exception as e:
                logger.debug(f"Meta API falló: {e}")

        # ─── Estrategia 2: Playwright Headless (PRINCIPAL) ────
        try:
            data = await self._playwright_extract(clean_handle)
            if data and data.get("followers", 0) > 0:
                logger.info(f"✅ Playwright: @{clean_handle} — {data['followers']} seguidores")
                return data
        except Exception as e:
            logger.warning(f"⚠️ Playwright falló para @{clean_handle}: {e}")

        # ─── Estrategia 3: LLM Scraper ────────────────────────
        try:
            data = await llm_scrape_profile(
                clean_handle,
                provider=LLM_PROVIDER,
                timeout=LLM_SCRAPER_TIMEOUT,
            )
            if data and data.get("followers", 0) > 0:
                logger.info(f"✅ LLM Scraper: @{clean_handle} — {data['followers']} seguidores")
                return data
        except Exception as e:
            logger.warning(f"⚠️ LLM Scraper falló para @{clean_handle}: {e}")

        logger.warning(f"❌ Todas las estrategias fallaron para @{clean_handle}")
        return None

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 1: Meta Graph API
    # ══════════════════════════════════════════════════════════

    async def _meta_graph_api_profile(self, handle: str) -> Optional[dict]:
        """Usa la API oficial de Meta (Profile Discovery)."""
        if not META_ACCESS_TOKEN:
            return None

        api_url = f"{self.META_GRAPH_API}/{self.META_API_VERSION}/profile_lookup"
        params = {
            "username": handle,
            "access_token": META_ACCESS_TOKEN,
            "fields": "id,username,name,follower_count,biography,profile_pic_url,threads_count",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.debug(f"Meta API respondió {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()

        if "data" in data:
            profile = data["data"]
            return {
                "handle": f"@{handle}",
                "name": profile.get("name", ""),
                "bio": profile.get("biography", ""),
                "followers": int(profile.get("follower_count", 0)),
                "posts": int(profile.get("threads_count", 0)),
                "profile_pic": profile.get("profile_pic_url", ""),
                "user_id": profile.get("id", ""),
                "source": "meta_api",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        return None

    async def _meta_graph_api_posts(self, handle: str, limit: int = 10) -> list[dict]:
        """Obtiene posts via Meta API."""
        if not META_ACCESS_TOKEN:
            return []

        api_url = f"{self.META_GRAPH_API}/{self.META_API_VERSION}/profile_posts"
        params = {
            "username": handle,
            "access_token": META_ACCESS_TOKEN,
            "fields": "id,text,media_urls,permalink,timestamp,like_count,reply_count,repost_count",
            "limit": min(limit, 25),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()

        posts = []
        for item in data.get("data", []):
            posts.append({
                "post_id": item.get("id", ""),
                "text": item.get("text", ""),
                "likes": int(item.get("like_count", 0)),
                "replies": int(item.get("reply_count", 0)),
                "reposts": int(item.get("repost_count", 0)),
                "has_image": bool(item.get("media_urls")),
                "has_video": False,
                "taken_at": item.get("timestamp", ""),
                "permalink": item.get("permalink", ""),
                "source": "meta_api",
            })

        return posts

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 2: Playwright Headless (PRINCIPAL)
    # ══════════════════════════════════════════════════════════

    async def _playwright_extract(self, handle: str) -> Optional[dict]:
        """
        Extrae perfil usando Playwright headless.
        Busca líneas que contengan variantes de "seguidores" y extrae números.
        Soporta: "509 mil seguidores", "1.2M followers", "509128 seguidores", etc.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.debug(f"⏭️ Playwright no disponible — saltando @{handle}")
            return None

        profile_url = f"{self.BASE_URL}/@{handle}"
        context = await playwright_manager.get_context(f"threads_{handle}")
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)

            if "/login" in page.url.lower():
                logger.warning(f"⛔ Login wall para @{handle}")
                return None

            title = await page.title()
            text = await page.evaluate("() => document.body.innerText")

            followers = 0
            following = 0

            # Recorrer líneas buscando "seguidores" / "followers" (ES o EN)
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Buscar línea que contenga "seguidores" o "followers"
                ll = line.lower()
                if "seguidores" in ll or "followers" in ll or "follower" in ll:
                    # Extraer números de la línea
                    # Puede ser: "509 mil seguidores", "1.2M seguidores", "509,128 seguidores"
                    nums = re.findall(r'[\d,.]+(?:\s*mil)?', line, re.IGNORECASE)
                    for n in nums:
                        n = n.strip()
                        mul = 1
                        # Detectar "mil" literal (español)
                        has_mil = False
                        if n.lower().endswith("mil"):
                            mul = 1_000
                            n = n[:-3].strip()
                            has_mil = True
                        # Detectar sufijos K/M/B
                        upper = n.upper()
                        if upper.endswith("M"):
                            mul = 1_000_000
                            n = n[:-1]
                        elif upper.endswith("K"):
                            mul = 1_000
                            n = n[:-1]
                        elif upper.endswith("B"):
                            mul = 1_000_000_000
                            n = n[:-1]
                        n = n.replace(",", "").replace(".", "")
                        try:
                            val = int(n) * mul
                        except ValueError:
                            continue
                        if val > followers:
                            followers = val
                    break  # Ya encontramos la línea de followers

            # Buscar "siguiendo" o "following"
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                ll = line.lower()
                if "siguiendo" in ll or "following" in ll:
                    nums = re.findall(r'\d+', line)
                    if nums:
                        try:
                            following = int(nums[0])
                        except ValueError:
                            pass
                    break

            # Extraer nombre del title: "El Espectador (@elespectador) • Threads, Say more"
            name = re.sub(
                rf"\s*\(@{handle}\)\s*•\s*Threads.*", "", title, flags=re.IGNORECASE
            ).strip()
            if not name or "Threads" in name:
                name = f"@{handle}"

            if followers > 0:
                logger.info(f"   ✅ @{handle}: {followers} seg | \"{title[:50]}\"")
                return {
                    "handle": f"@{handle}",
                    "name": name,
                    "bio": "",
                    "followers": followers,
                    "following": following,
                    "posts": 0,
                    "profile_pic": "",
                    "user_id": "",
                    "source": "playwright_dom",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "title": title,
                }

            logger.warning(f"⚠️ @{handle}: página cargada sin datos de seguidores")
            return None

        except Exception as e:
            logger.error(f"❌ @{handle}: error: {type(e).__name__}: {e}")
            return None
        finally:
            await page.close()

    async def _playwright_extract_posts(self, handle: str, limit: int = 10) -> list[dict]:
        """Extrae posts usando Playwright con auto-scroll."""
        if not PLAYWRIGHT_AVAILABLE:
            return []

        profile_url = f"{self.BASE_URL}/@{handle}"
        context = await playwright_manager.get_context(f"threads_posts_{handle}")
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)

            if "/login" in page.url:
                return []

            await _a_jitter_delay(3, 5)

            # Auto-scroll para cargar posts
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await _a_jitter_delay(2, 4)

            html = await page.content()

            # Extraer threads del hidden JSON
            hidden_data = _extract_from_hidden_json(html)
            if not hidden_data:
                return []

            all_threads = []

            def collect_threads(obj):
                if isinstance(obj, dict):
                    if obj.get("thread_items") and isinstance(obj["thread_items"], list):
                        for ti in obj["thread_items"]:
                            if isinstance(ti, dict) and "post" in ti:
                                all_threads.append(ti["post"])
                    for v in obj.values():
                        collect_threads(v)
                elif isinstance(obj, list):
                    for item in obj:
                        collect_threads(item)

            collect_threads(hidden_data)

            posts = []
            for thread in all_threads[:limit]:
                posts.append({
                    "post_id": str(thread.get("id", thread.get("pk", ""))),
                    "text": thread.get("text", thread.get("caption", "")),
                    "likes": int(thread.get("like_count", thread.get("likes", 0))),
                    "replies": int(thread.get("reply_count", thread.get("replies", 0))),
                    "reposts": int(thread.get("repost_count", thread.get("reposts", 0))),
                    "has_image": bool(thread.get("image_urls") or thread.get("carousel_media")),
                    "has_video": bool(thread.get("video_url")),
                    "permalink": thread.get("permalink", ""),
                    "source": "playwright",
                })

            return posts

        finally:
            await page.close()


# ══════════════════════════════════════════════════════════════
# API Pública
# ══════════════════════════════════════════════════════════════

_scraper_instance: Optional[ThreadsScraperPremium] = None


def _get_scraper() -> ThreadsScraperPremium:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = ThreadsScraperPremium()
    return _scraper_instance


async def scrape_threads_profile(handle: str) -> Optional[dict]:
    """Scrapea perfil de Threads."""
    return await _get_scraper().scrape_profile(handle)


async def scrape_threads_posts(handle: str, limit: int = 10) -> list[dict]:
    """Scrapea posts recientes de Threads."""
    clean_handle = handle.lstrip("@")
    scraper = _get_scraper()

    # Meta API (si hay token)
    if META_ACCESS_TOKEN:
        try:
            posts = await scraper._meta_graph_api_posts(clean_handle, limit)
            if posts:
                return posts
        except Exception:
            pass

    # Playwright (principal)
    try:
        posts = await scraper._playwright_extract_posts(clean_handle, limit)
        if posts:
            return posts
    except Exception:
        pass

    return []
