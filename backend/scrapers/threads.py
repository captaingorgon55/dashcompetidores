"""
Threads Scraper v3 — Premium — Extracción profunda con Playwright.

Arquitectura de estrategias (fallback chain):

  ┌─ 1. Meta Graph API (Opcional — requiere App aprobada)
  │     GET /{api-version}/{user-id}/profile_lookup?username={username}
  │
  ├─ 2. LLM Scraper (Nuevo!)
  │     Node.js + Playwright + LLM (Groq/OpenAI/Gemini)
  │     Extracción inteligente: HTML o screenshot (multimodal)
  │     ✅ Gratis via Groq (Llama 3.3 70B)
  │
  ├─ 3. Playwright Headless
  │     ├─ Network Interception → captura respuestas GraphQL en vivo
  │     ├─ Hidden JSON → extrae <script type="application/json" data-sjs>
  │     └─ Anti-detección avanzada
  │
  ├─ 4. oEmbed API
  │     GET https://threads.com/api/oembed?url=...
  │     → datos embed via Playwright
  │
  ├─ 5. httpx GraphQL Directo
  │     POST https://www.threads.com/api/graphql
  │     → doc_ids, rotating UAs, backoff
  │
  └─ 6. Static HTML (Último recurso)
        BeautifulSoup + meta tags + JSON-LD

Mejoras v3:
  ✅ Navegador headless real (JS ejecutado)
  ✅ Captura de JSON oculto (data-sjs)
  ✅ Network interception para GraphQL
  ✅ Rotación de User-Agents
  ✅ Jitter + backoff exponencial
  ✅ Proxy support
  ✅ Auto-scroll para posts
  ✅ Extracción de contenido real (texto, imágenes, engagement)
"""

import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.config import (
    USER_AGENTS, MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    MAX_RETRIES, META_APP_ID, META_ACCESS_TOKEN, PROXY_URL,
    PLAYWRIGHT_TIMEOUT_MS, LLM_PROVIDER, LLM_API_KEY, LLM_SCRAPER_TIMEOUT,
)
from backend.scrapers.llm_scraper_bridge import llm_scrape_profile, llm_scrape_posts

# Playwright es OPCIONAL — en servidores con 512MB lo quitamos de requirements.txt
# para ahorrar ~300MB en la descarga de Chromium.
# Sin Playwright, el scraper salta Estrategias 3 y 4 (browser-based) y
# depende de llm-scraper (Node.js) para extracción con navegador.
PLAYWRIGHT_AVAILABLE = False
playwright_manager = None
try:
    from backend.scrapers.playwright_manager import playwright_manager
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.info("ℹ️ Playwright no disponible — estrategias 3 y 4 saltadas. Usar llm-scraper para browser.")

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Utilidades
# ══════════════════════════════════════════════════════════════

def _get_random_ua() -> str:
    """Retorna un User-Agent aleatorio de la lista configurada."""
    return random.choice(USER_AGENTS)


def _jitter_delay(base_min: float = None, base_max: float = None):
    """Pausa con jitter aleatorio para evitar rate limiting."""
    min_d = base_min or MIN_DELAY_BETWEEN_REQUESTS
    max_d = base_max or MAX_DELAY_BETWEEN_REQUESTS
    delay = random.uniform(min_d, max_d)
    time.sleep(delay)


async def _a_jitter_delay(base_min: float = None, base_max: float = None):
    """Versión async del jitter delay."""
    min_d = base_min or MIN_DELAY_BETWEEN_REQUESTS
    max_d = base_max or MAX_DELAY_BETWEEN_REQUESTS
    delay = random.uniform(min_d, max_d)
    await asyncio.sleep(delay)


def _exponential_backoff(attempt: int, base_delay: float = 2.0) -> float:
    """Calcula delay con backoff exponencial: 2^attempt * base_delay + jitter."""
    return (base_delay * (2 ** attempt)) + random.uniform(0, 1)


def _parse_count(text) -> int:
    """Parsea strings como '1.2M', '500K', '1,234' a enteros.

    Estrategia:
    1. Extraer el sufijo (K, M, B, MIL) ANTES de limpiar decimales
    2. Limpiar solo comas (separadores de miles)
    3. El punto decimal se conserva para float()
    """
    if not text:
        return 0
    if isinstance(text, (int, float)):
        return int(text)

    raw = str(text).strip().upper()

    multipliers = {"B": 1_000_000_000, "M": 1_000_000, "K": 1_000, "MIL": 1_000}

    # 1. Detectar sufijo primero
    suffix = ""
    for s in sorted(multipliers, key=len, reverse=True):
        if raw.endswith(s):
            suffix = s
            break

    # 2. Extraer la parte numérica y limpiar
    if suffix:
        number_str = raw[:-len(suffix)].rstrip("S")  # quitar "S" de "MIL" plural
    else:
        number_str = raw

    # 3. Limpiar solo comas (separador de miles), conservar punto decimal
    number_str = number_str.replace(",", "").replace(".", ".")  # no-op, solo claridad

    try:
        value = float(number_str)
        if suffix:
            return int(value * multipliers[suffix])
        return int(value)
    except ValueError:
        return 0


def _extract_from_hidden_json(html: str) -> Optional[dict]:
    """
    Extrae datos estructurados de los <script type="application/json" data-sjs>.
    Threads embebe TODOS los datos de la página en estos scripts JSON.

    Returns: dict con los datos combinados de todos los scripts JSON encontrados.
    """
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/json")

    combined = {}
    for script in scripts:
        if not script.string:
            continue
        # Filtrar scripts con data-sjs (contienen datos reales)
        if script.get("data-sjs") is None and not any(
            key in (script.string[:500]) for key in ["user", "thread", "follower"]
        ):
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                combined.update(data)
            elif isinstance(data, list):
                combined["_list_items"] = data
        except (json.JSONDecodeError, AttributeError):
            continue

    return combined if combined else None


def _deep_find(obj, target_keys: set, max_depth: int = 20, _depth: int = 0):
    """
    Búsqueda recursiva profunda limitada en estructuras JSON.
    Retorna el primer dict que contenga TODOS los target_keys.
    """
    if _depth > max_depth:
        return None
    if isinstance(obj, dict):
        if target_keys.issubset(obj.keys()):
            # Verificar que tenga valores reales
            if any(obj.get(k) for k in target_keys):
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
# Scraper Premium
# ══════════════════════════════════════════════════════════════

class ThreadsScraperPremium:
    """
    Scraper premium de Threads con múltiples estrategias de extracción.

    Características:
    - Rotación de User-Agents
    - Jitter y backoff exponencial
    - Playwright headless (JS real)
    - Network interception (captura GraphQL)
    - Hidden JSON parsing (data-sjs)
    - oEmbed API fallback
    - GraphQL directo (httpx)
    - Proxy support
    """

    BASE_URL = "https://www.threads.com"
    GRAPHQL_URL = "https://www.threads.com/api/graphql"
    OEMBED_URL = "https://threads.com/api/oembed"
    IG_APP_ID = "238260118697367"
    META_GRAPH_API = "https://graph.threads.net"
    META_API_VERSION = "v21.0"

    # Doc IDs conocidos
    PROFILE_DOC_IDS = [
        "23996318473300828",
        "23996318473300827",
    ]
    POSTS_DOC_ID = "6232751443445612"
    REPLIES_DOC_ID = "6307072669391286"

    def __init__(self):
        self._last_request_time = 0.0
        self._httpx_client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Obtiene (o crea) un cliente httpx con UA rotado."""
        if self._httpx_client is None or not hasattr(self._httpx_client, 'headers'):
            self._httpx_client = httpx.Client(
                headers={
                    "User-Agent": _get_random_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "x-ig-app-id": self.IG_APP_ID,
                    "x-asbd-id": "129477",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                },
                follow_redirects=True,
                timeout=30.0,
            )
        return self._httpx_client

    def _rotate_ua(self):
        """Rota el User-Agent del cliente httpx."""
        if self._httpx_client:
            self._httpx_client.headers["User-Agent"] = _get_random_ua()

    async def scrape_profile(self, handle: str) -> Optional[dict]:
        """
        Scrapea datos completos de un perfil de Threads.
        Usa la cadena de estrategias hasta que una funcione.
        """
        clean_handle = handle.lstrip("@")
        logger.info(f"🔍 Scrapeando perfil @{clean_handle}...")

        # ─── Estrategia 1: Meta Graph API ─────────────────────
        if META_ACCESS_TOKEN:
            try:
                data = await self._meta_graph_api_profile(clean_handle)
                if data:
                    logger.info(f"✅ Meta API: @{clean_handle} — {data.get('followers', 0)} seguidores")
                    return data
            except Exception as e:
                logger.debug(f"Meta API falló: {e}")

        # ─── Estrategia 2: LLM Scraper (Node.js) ──────────────
        # Usa llm-scraper + Groq/OpenAI para extracción inteligente vía LLM.
        # Groq tiene free tier (gratis), OpenAI requiere OPENAI_API_KEY.
        # El LLM entiende la página aunque tenga anti-bot, y puede
        # incluso usar screenshot (multimodal) si el HTML está ofuscado.
        try:
            data = await llm_scrape_profile(
                clean_handle,
                provider=LLM_PROVIDER,
                timeout=LLM_SCRAPER_TIMEOUT,
            )
            if data and data.get("followers", 0) > 0:
                logger.info(f"✅ LLM Scraper: @{clean_handle} — {data.get('followers', 0)} seguidores")
                return data
        except Exception as e:
            logger.warning(f"⚠️ LLM Scraper falló para @{clean_handle}: {e}")

        # Flag: si Playwright detectó login wall, saltar estrategias httpx
        login_detected = False

        # ─── Estrategia 3: Playwright Headless ────────────────
        if PLAYWRIGHT_AVAILABLE:
            try:
                data = await self._playwright_extract(clean_handle)
                if data and data.get("followers", 0) > 0:
                    logger.info(f"✅ Playwright: @{clean_handle} — {data.get('followers', 0)} seguidores")
                    return data
                if data is None:
                    # Si Playwright devolvió None pero no lanzó excepción,
                    # probablemente fue redirigido a login
                    login_detected = True
            except Exception as e:
                logger.warning(f"⚠️ Playwright falló para @{clean_handle}: {e}")
        else:
            logger.debug(f"⏭️ Playwright no disponible — saltando Estrategia 3 para @{clean_handle}")

        # ─── Estrategia 4: oEmbed (Playwright) ────────────────
        if not login_detected and PLAYWRIGHT_AVAILABLE:
            try:
                data = await self._oembed_extract(clean_handle)
                if data:
                    logger.info(f"✅ oEmbed: @{clean_handle}")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ oEmbed falló para @{clean_handle}: {e}")
        elif not PLAYWRIGHT_AVAILABLE:
            logger.debug(f"⏭️ Playwright no disponible — saltando Estrategia 4 para @{clean_handle}")

        # ─── Estrategias httpx (5 y 6) ────────────────────────
        # threads.com bloquea httpx (redirect a login), saltar si ya detectamos login
        if login_detected:
            logger.warning(f"⛔ threads.com bloquea httpx para @{clean_handle} — saltando estrategias 5 y 6")
            return None

        # Estrategia 5: GraphQL Directo
        try:
            user_id = self._resolve_user_id(clean_handle)
            if user_id:
                data = self._fetch_via_graphql(user_id, clean_handle)
                if data:
                    logger.info(f"✅ GraphQL: @{clean_handle} — {data.get('followers', 0)} seguidores")
                    return data
        except Exception as e:
            logger.debug(f"GraphQL falló: {e}")

        # Estrategia 6: Static HTML
        try:
            data = self._fallback_extract(clean_handle)
            if data and data.get("followers", 0) > 0:
                logger.info(f"✅ HTML fallback: @{clean_handle} — {data.get('followers', 0)} seguidores")
                return data
        except Exception as e:
            logger.debug(f"HTML fallback falló: {e}")

        logger.warning(f"❌ Todas las estrategias fallaron para @{clean_handle}")
        return None

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 1: Meta Graph API
    # ══════════════════════════════════════════════════════════

    async def _meta_graph_api_profile(self, handle: str) -> Optional[dict]:
        """
        Usa la API oficial de Meta (Profile Discovery).
        Requiere META_ACCESS_TOKEN con permisos threads_profile_discovery.

        Endpoints:
        GET /{api-version}/{user-id}/profile_lookup?username={username}
        """
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
        """Obtiene posts via Meta API Profile Posts endpoint."""
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
    # ESTRATEGIA 2: Playwright Headless
    # ══════════════════════════════════════════════════════════

    async def _playwright_extract(self, handle: str) -> Optional[dict]:
        """
        Extrae datos usando Playwright headless con:
        1. Network interception → captura respuestas del endpoint GraphQL
        2. Hidden JSON → <script type="application/json" data-sjs>
        3. Page content → meta tags y texto visible
        """
        profile_url = f"{self.BASE_URL}/@{handle}"

        context = await playwright_manager.get_context(f"threads_{handle}")

        # Configurar network interception
        graphql_responses = []

        async def intercept_response(response):
            if "/api/graphql" in response.url:
                try:
                    body = await response.json()
                    graphql_responses.append(body)
                except Exception:
                    pass

        page = await context.new_page()

        try:
            page.on("response", intercept_response)

            # Navegar al perfil
            await page.goto(
                profile_url,
                wait_until="networkidle",
                timeout=PLAYWRIGHT_TIMEOUT_MS,
            )

            # Detectar si nos redirigieron al login
            if "/login" in page.url:
                logger.warning(f"⛔ Redirigido a login para @{handle} (page.url={page.url})")
                return None

            # Esperar un poco para que carguen los scripts dinámicos
            await _a_jitter_delay(2, 4)

            # Obtener HTML después de renderizado JS
            html = await page.content()

            # Obtener el título de la página
            title = await page.title()

            # Intentar extraer texto visible de la página
            page_text = await page.evaluate("() => document.body.innerText")

            # ─── Extraer de Hidden JSON (data-sjs) ────────
            hidden_data = _extract_from_hidden_json(html)

            profile = None

            # Buscar en hidden JSON primero
            if hidden_data:
                profile = _deep_find(hidden_data, {
                    "follower_count", "username", "pk"
                })
                if not profile:
                    # Intentar con menos keys
                    profile = _deep_find(hidden_data, {
                        "follower_count", "pk"
                    })

            # Buscar en respuestas GraphQL interceptadas
            if not profile and graphql_responses:
                for gql_resp in graphql_responses:
                    profile = _deep_find(gql_resp, {
                        "follower_count", "username", "pk"
                    })
                    if profile:
                        break

            # Si encontramos datos, construir resultado
            if profile:
                return {
                    "handle": f"@{handle}",
                    "name": profile.get("full_name", profile.get("name", "")),
                    "bio": profile.get("biography", profile.get("bio", "")),
                    "followers": int(profile.get("follower_count", 0)),
                    "following": int(profile.get("following_count", 0)),
                    "posts": int(profile.get("threads_count", profile.get("media_count", 0))),
                    "profile_pic": profile.get("profile_pic_url", profile.get("profile_picture", "")),
                    "user_id": str(profile.get("pk", profile.get("id", ""))),
                    "source": "playwright_graphql",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "title": title,
                }

            # Extraer del texto visible de la página
            followers = 0
            posts = 0

            # Buscar patrones de seguidores en el texto visible
            follower_patterns = [
                r'(\d[\d,.]*[KMBkmb]?)\s*(?:seguidores|follower|followers)',
                r'(?:seguidores|follower|followers)\s*(\d[\d,.]*[KMBkmb]?)',
            ]
            for pattern in follower_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    followers = _parse_count(match.group(1))
                    if followers > 0:
                        break

            # Buscar posts
            post_patterns = [
                r'(\d[\d,.]*)\s*(?:publicaciones|posts|threads)',
            ]
            for pattern in post_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    posts = _parse_count(match.group(1))
                    break

            # Extraer nombre de meta tags
            name = title.replace(f"(@{handle})", "").replace(f"(@{handle.lower()})", "").strip()
            if "Threads" in name:
                name = f"@{handle}"

            if followers > 0:
                return {
                    "handle": f"@{handle}",
                    "name": name.strip(" |"),
                    "bio": "",
                    "followers": followers,
                    "following": 0,
                    "posts": posts,
                    "profile_pic": "",
                    "user_id": "",
                    "source": "playwright_text",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "title": title,
                }

            return None

        finally:
            await page.close()

    async def _playwright_extract_posts(self, handle: str, limit: int = 10) -> list[dict]:
        """Extrae posts usando Playwright con auto-scroll + network intercept."""
        profile_url = f"{self.BASE_URL}/@{handle}"

        context = await playwright_manager.get_context(f"threads_posts_{handle}")
        graphql_responses = []

        async def intercept_response(response):
            if "/api/graphql" in response.url:
                try:
                    body = await response.json()
                    graphql_responses.append(body)
                except Exception:
                    pass

        page = await context.new_page()

        try:
            page.on("response", intercept_response)
            await page.goto(
                profile_url,
                wait_until="networkidle",
                timeout=PLAYWRIGHT_TIMEOUT_MS,
            )

            # Detectar si nos redirigieron al login
            if "/login" in page.url:
                logger.warning(f"⛔ Redirigido a login para posts de @{handle}")
                return []

            await _a_jitter_delay(3, 5)

            # Auto-scroll para cargar más posts
            for scroll_attempt in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await _a_jitter_delay(2, 4)

            html = await page.content()
            page_text = await page.evaluate("() => document.body.innerText")

            posts = []

            # 1. Intentar extraer de hidden JSON
            hidden_data = _extract_from_hidden_json(html)
            if hidden_data:
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
                for thread in all_threads[:limit]:
                    posts.append(self._parse_thread(thread))

            # 2. Intentar de GraphQL interceptado
            if not posts and graphql_responses:
                for gql_resp in graphql_responses:
                    all_threads = []
                    collect_threads(gql_resp)
                    for thread in all_threads[:limit]:
                        posts.append(self._parse_thread(thread))
                    if posts:
                        break

            return posts

        finally:
            await page.close()

    @staticmethod
    def _normalize_timestamp(ts) -> Optional[int]:
        """Normaliza cualquier formato de timestamp a Unix epoch (int).

        Acepta:
        - int/float (timestamp Unix)
        - str ISO 8601 ("2025-01-15T10:30:00+00:00")
        - str Unix timestamp ("1736933400")
        - datetime object
        """
        if ts is None or ts == "":
            return None

        # Ya es timestamp numérico
        if isinstance(ts, (int, float)):
            # Si es > 1e12, probablemente es milisegundos
            if ts > 1_000_000_000_000:
                return int(ts / 1000)
            return int(ts)

        # datetime object
        if hasattr(ts, 'timestamp'):
            return int(ts.timestamp())

        # String ISO o timestamp string
        if isinstance(ts, str):
            ts = ts.strip()
            # Intentar como timestamp numérico string
            if ts.replace(".", "").replace("-", "").isdigit() and len(ts) >= 10:
                try:
                    val = float(ts)
                    if val > 1_000_000_000_000:
                        return int(val / 1000)
                    return int(val)
                except ValueError:
                    pass

            # ISO 8601
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return int(dt.timestamp())
            except (ValueError, TypeError):
                pass

        return None

    def _parse_thread(self, thread: dict) -> dict:
        """Parsea un thread/post individual en formato estandarizado."""
        taken_at = self._normalize_timestamp(
            thread.get("taken_at", thread.get("timestamp", None))
        )
        return {
            "post_id": str(thread.get("id", thread.get("pk", ""))),
            "text": thread.get("text", thread.get("caption", thread.get("caption_text", ""))),
            "likes": int(thread.get("like_count", thread.get("likes", 0))),
            "replies": int(thread.get("reply_count", thread.get("replies", 0))),
            "reposts": int(thread.get("repost_count", thread.get("reposts", 0))),
            "views": int(thread.get("view_count", thread.get("views", 0))),
            "has_image": bool(
                thread.get("image_urls") or thread.get("carousel_media") or
                thread.get("media_urls") or thread.get("has_image")
            ),
            "has_video": bool(
                thread.get("video_url") or thread.get("has_video")
            ),
            "taken_at": taken_at,
            "permalink": thread.get("permalink", ""),
            "source": "playwright",
        }

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 3: oEmbed API
    # ══════════════════════════════════════════════════════════

    async def _oembed_extract(self, handle: str) -> Optional[dict]:
        """
        Usa la API oEmbed de Threads (tokenless) via Playwright.
        threads.com bloquea httpx (redirige a login), así que usamos
        el navegador para obtener la respuesta JSON del oEmbed.

        Endpoint:
        GET https://threads.com/api/oembed?url=https://threads.com/@{handle}
        """
        oembed_url = f"{self.OEMBED_URL}"
        params = {
            "url": f"{self.BASE_URL}/@{handle}",
            "format": "json",
        }

        # Intentar con Playwright primero (threads.com bloquea httpx)
        try:
            context = await playwright_manager.get_context(f"oembed_{handle}")
            page = await context.new_page()
            try:
                full_url = f"{oembed_url}?url={self.BASE_URL}/@{handle}&format=json"
                resp = await page.goto(full_url, wait_until="networkidle", timeout=15000)

                # Verificar si redirigió a login
                if "/login/" in page.url:
                    logger.debug(f"oEmbed redirigió a login para @{handle}")
                    # Seguir con fallback httpx
                    raise Exception("oEmbed login redirect")

                # Verificar que no sea HTML (login page)
                content_type = resp.headers.get("content-type", "").lower() if resp else ""
                if resp and resp.ok and "text/html" not in content_type:
                    body = await page.evaluate("() => document.body.innerText")
                    data = json.loads(body)
                    if data.get("author_name"):
                        return {
                            "handle": f"@{handle}",
                            "name": data.get("author_name", "").replace(f"(@{handle})", "").strip(" |") or f"@{handle}",
                            "bio": data.get("title", ""),
                            "followers": 0,
                            "posts": 0,
                            "profile_pic": data.get("thumbnail_url", ""),
                            "source": "oembed",
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }
            except Exception:
                pass
            finally:
                await page.close()
        except Exception:
            pass

        # Fallback con httpx (por si threads.net aún funciona)
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://threads.net/api/oembed",
                    params={"url": f"https://www.threads.net/@{handle}", "format": "json"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("author_name"):
                        return {
                            "handle": f"@{handle}",
                            "name": data.get("author_name", "").replace(f"(@{handle})", "").strip(" |") or f"@{handle}",
                            "bio": data.get("title", ""),
                            "followers": 0,
                            "posts": 0,
                            "profile_pic": data.get("thumbnail_url", ""),
                            "source": "oembed_legacy",
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }
            except Exception:
                pass

        return None

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 4: GraphQL Directo (httpx)
    # ══════════════════════════════════════════════════════════

    def _resolve_user_id(self, handle: str) -> Optional[str]:
        """Obtiene userID desde la página HTML del perfil."""
        client = self._get_client()
        url = f"{self.BASE_URL}/@{handle}"
        _jitter_delay()

        for attempt in range(MAX_RETRIES):
            try:
                self._rotate_ua()
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text

                # Buscar en scripts
                patterns = [
                    r'"userID"\s*:\s*"(\d+)"',
                    r'"pk"\s*:\s*(\d+)',
                    r'"id"\s*:\s*"(\d{10,})"',
                ]

                for pattern in patterns:
                    match = re.search(pattern, html)
                    if match:
                        return match.group(1)

                # Buscar en script tags
                soup = BeautifulSoup(html, "lxml")
                for script in soup.find_all("script"):
                    if not script.string:
                        continue
                    for pattern in patterns:
                        match = re.search(pattern, script.string)
                        if match:
                            return match.group(1)

                if attempt < MAX_RETRIES - 1:
                    backoff = _exponential_backoff(attempt)
                    logger.debug(f"Retry {attempt+1} para userID @{handle} en {backoff:.1f}s")
                    time.sleep(backoff)

            except Exception as e:
                logger.debug(f"Error resolviendo userID @{handle} (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_exponential_backoff(attempt))

        return None

    def _fetch_via_graphql(self, user_id: str, handle: str) -> Optional[dict]:
        """Consulta el endpoint GraphQL interno de Threads."""
        for doc_id in self.PROFILE_DOC_IDS:
            for attempt in range(MAX_RETRIES):
                try:
                    self._rotate_ua()
                    _jitter_delay()

                    variables = json.dumps({"userID": user_id})
                    payload = {"doc_id": doc_id, "variables": variables}

                    client = self._get_client()
                    resp = client.post(
                        self.GRAPHQL_URL,
                        data=payload,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

                    if resp.status_code != 200:
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(_exponential_backoff(attempt))
                        continue

                    result = resp.json()
                    profile = _deep_find(result, {"follower_count", "username", "pk"})
                    if profile:
                        return {
                            "handle": f"@{handle}",
                            "name": profile.get("full_name", ""),
                            "bio": profile.get("biography", ""),
                            "followers": int(profile.get("follower_count", 0)),
                            "following": int(profile.get("following_count", 0)),
                            "posts": int(profile.get("threads_count", profile.get("media_count", 0))),
                            "profile_pic": profile.get("profile_pic_url", ""),
                            "user_id": str(profile.get("pk", "")),
                            "source": "graphql_direct",
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }

                except Exception as e:
                    logger.debug(f"GraphQL error (doc_id={doc_id}, attempt={attempt+1}): {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(_exponential_backoff(attempt))

        return None

    def _fetch_posts_via_graphql(self, user_id: str, handle: str, limit: int = 10) -> list[dict]:
        """Obtiene posts via GraphQL directo."""
        for attempt in range(MAX_RETRIES):
            try:
                self._rotate_ua()
                _jitter_delay()

                variables = json.dumps({"userID": user_id})
                payload = {"doc_id": self.POSTS_DOC_ID, "variables": variables}

                client = self._get_client()
                resp = client.post(
                    self.GRAPHQL_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if resp.status_code != 200:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(_exponential_backoff(attempt))
                    continue

                result = resp.json()

                # Extraer threads de la respuesta
                all_threads = []
                def collect(obj):
                    if isinstance(obj, dict):
                        if obj.get("thread_items") and isinstance(obj["thread_items"], list):
                            for ti in obj["thread_items"]:
                                if isinstance(ti, dict) and "post" in ti:
                                    all_threads.append(ti["post"])
                        if obj.get("threads") and isinstance(obj["threads"], list):
                            all_threads.extend(obj["threads"])
                        for v in obj.values():
                            collect(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            collect(item)

                collect(result)
                return [self._parse_thread(t) for t in all_threads[:limit]]

            except Exception as e:
                logger.debug(f"Posts GraphQL error (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_exponential_backoff(attempt))

        return []

    # ══════════════════════════════════════════════════════════
    # ESTRATEGIA 5: Static HTML Fallback
    # ══════════════════════════════════════════════════════════

    def _fallback_extract(self, handle: str) -> Optional[dict]:
        """Último recurso: extrae datos del HTML estático."""
        client = self._get_client()
        url = f"{self.BASE_URL}/@{handle}"

        for attempt in range(MAX_RETRIES):
            try:
                self._rotate_ua()
                _jitter_delay()
                resp = client.get(url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")
                text = soup.get_text()

                data = {
                    "handle": f"@{handle}",
                    "name": "",
                    "bio": "",
                    "followers": 0,
                    "following": 0,
                    "posts": 0,
                    "source": "fallback_html",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }

                # Intentar hidden JSON primero
                hidden = _extract_from_hidden_json(resp.text)
                if hidden:
                    profile = _deep_find(hidden, {"follower_count", "pk"})
                    if profile:
                        data["followers"] = int(profile.get("follower_count", 0))
                        data["name"] = profile.get("full_name", profile.get("name", ""))
                        data["bio"] = profile.get("biography", "")
                        data["posts"] = int(profile.get("threads_count", 0))
                        data["profile_pic"] = profile.get("profile_pic_url", "")
                        data["source"] = "fallback_hidden_json"
                        return data

                # Meta tags
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    data["name"] = og_title.get("content", "")

                og_desc = soup.find("meta", property="og:description")
                if og_desc:
                    data["bio"] = og_desc.get("content", "")

                # Patrones de seguidores
                for pattern in [
                    r'(\d[\d,.]*[KMBkmb]?)\s*(?:seguidores|follower|followers)',
                    r'(?:seguidores|follower|followers)\s*(\d[\d,.]*[KMBkmb]?)',
                ]:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        count = _parse_count(match.group(1))
                        if count > 0:
                            data["followers"] = count
                            break

                # Patrones de posts
                for pattern in [
                    r'(\d[\d,.]*)\s*(?:publicaciones|posts|threads)',
                ]:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        data["posts"] = _parse_count(match.group(1))
                        break

                if data["followers"] > 0:
                    return data

            except Exception as e:
                logger.debug(f"HTML fallback error (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_exponential_backoff(attempt))

        return None

    def close(self):
        """Limpia recursos del scraper."""
        if self._httpx_client:
            try:
                self._httpx_client.close()
            except Exception:
                pass
            self._httpx_client = None


# ══════════════════════════════════════════════════════════════
# API Pública (async)
# ══════════════════════════════════════════════════════════════

async def scrape_threads_profile(handle: str) -> Optional[dict]:
    """Scrapea perfil de Threads usando el scraper premium."""
    scraper = ThreadsScraperPremium()
    try:
        return await scraper.scrape_profile(handle)
    finally:
        scraper.close()


async def scrape_threads_posts(handle: str, limit: int = 10) -> list[dict]:
    """Scrapea posts recientes de Threads usando el scraper premium."""
    clean_handle = handle.lstrip("@")
    scraper = ThreadsScraperPremium()

    try:
        # Intentar Meta API primero
        if META_ACCESS_TOKEN:
            try:
                posts = await scraper._meta_graph_api_posts(clean_handle, limit)
                if posts:
                    return posts
            except Exception:
                pass

        # Playwright headless (solo si está disponible)
        if PLAYWRIGHT_AVAILABLE:
            try:
                posts = await scraper._playwright_extract_posts(clean_handle, limit)
                if posts:
                    return posts
            except Exception:
                pass
        else:
            logger.debug(f"⏭️ Playwright no disponible — saltando extracción de posts para @{clean_handle}")

        # GraphQL directo
        user_id = await asyncio.get_event_loop().run_in_executor(
            None, scraper._resolve_user_id, clean_handle
        )
        if user_id:
            posts = await asyncio.get_event_loop().run_in_executor(
                None, scraper._fetch_posts_via_graphql, user_id, clean_handle, limit
            )
            return posts

        return []
    finally:
        scraper.close()
