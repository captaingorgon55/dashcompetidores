"""
Threads Scraper v2 — Extracción de datos reales vía GraphQL API interna.

Usa el endpoint interno de GraphQL de Threads para obtener datos públicos
de perfil: seguidores, siguiendo, posts, y métricas de engagement.

Threads no tiene API pública oficial para leer datos de otros perfiles,
pero su interfaz web usa GraphQL interno con Doc IDs identificables.

Referencia: https://github.com/m1guelpf/threads-api
"""

import re
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.config import USER_AGENT

logger = logging.getLogger(__name__)


class ThreadsScraper:
    """Scrapes public profile data from Threads.net usando GraphQL interno."""

    BASE_URL = "https://www.threads.net"
    GRAPHQL_URL = "https://www.threads.net/api/graphql"
    IG_APP_ID = "238260118697367"

    # Doc IDs known for Threads GraphQL queries (may change, multiples como fallback)
    PROFILE_DOC_IDS = ["23996318473300828", "23996318473300827"]

    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
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

    def scrape_profile(self, handle: str) -> Optional[dict]:
        """
        Scrapea datos públicos de un perfil de Threads.

        Args:
            handle: @handle o handle sin @

        Returns:
            dict con datos del perfil o None si falla
        """
        clean_handle = handle.lstrip("@")

        # Estrategia 1: Obtener userID desde la página del perfil
        user_id = self._resolve_user_id(clean_handle)
        if not user_id:
            logger.warning(f"No se pudo resolver userID para @{clean_handle}")
            return self._fallback_extract(clean_handle)

        # Estrategia 2: Consultar GraphQL con el userID
        profile_data = self._fetch_via_graphql(user_id, clean_handle)
        if profile_data:
            return profile_data

        # Estrategia 3: Fallback a scraping de página
        logger.info(f"Fallback a scraping de página para @{clean_handle}")
        return self._fallback_extract(clean_handle)

    def _resolve_user_id(self, handle: str) -> Optional[str]:
        """
        Obtiene el userID de Threads desde la página del perfil.
        Busca en los scripts embedidos y meta tags.
        """
        url = f"{self.BASE_URL}/@{handle}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Error fetching profile page @{handle}: {e}")
            return None

        html = resp.text

        # Buscar en scripts con datos JSON embedidos
        patterns = [
            r'"userID"\s*:\s*"(\d+)"',
            r'"id"\s*:\s*"(\d+)"',
            r'"user_id"\s*:\s*(\d+)',
            r'"pk"\s*:\s*(\d+)',
        ]

        # Buscar en script tags
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            if not script.string:
                continue
            text = script.string
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)

            # Buscar en datos JSON grandes
            if "userID" in text or "user_id" in text or '"pk"' in text:
                # Intentar extraer objeto JSON que contenga el userID
                for pattern in [
                    r'"userID"\s*:\s*"(\d+)"',
                    r'"pk"\s*:\s*(\d+)',
                ]:
                    match = re.search(pattern, text)
                    if match:
                        return match.group(1)

        return None

    def _fetch_via_graphql(self, user_id: str, handle: str) -> Optional[dict]:
        """
        Consulta el endpoint GraphQL interno de Threads.
        """
        for doc_id in self.PROFILE_DOC_IDS:
            try:
                data = self._graphql_request(doc_id, user_id, handle)
                if data:
                    return self._parse_graphql_response(data, handle)
            except Exception as e:
                logger.debug(f"GraphQL con Doc ID {doc_id} falló: {e}")
                continue

        return None

    def _graphql_request(self, doc_id: str, user_id: str, handle: str) -> Optional[dict]:
        """
        Realiza la petición GraphQL a Threads.

        Variables típicas:
        {"userID": "userId"}
        """
        variables = json.dumps({"userID": user_id})
        payload = {
            "doc_id": doc_id,
            "variables": variables,
        }

        try:
            resp = self.client.post(
                self.GRAPHQL_URL,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code != 200:
                logger.debug(f"GraphQL respondió {resp.status_code} para Doc ID {doc_id}")
                return None

            result = resp.json()
            return result
        except Exception as e:
            logger.debug(f"Error en GraphQL request con Doc ID {doc_id}: {e}")
            return None

    def _parse_graphql_response(self, data: dict, handle: str) -> Optional[dict]:
        """
        Parsea la respuesta GraphQL para extraer datos del perfil.

        La estructura varía según el Doc ID usado, así que navegamos
        recursivamente buscando los campos que nos interesan.
        """
        profile = self._deep_search(data, {
            "username": handle,
            "follower_count": None,
            "following_count": None,
            "post_count": None,
            "full_name": None,
            "biography": None,
            "profile_pic_url": None,
            "pk": None,
        })

        if profile and profile.get("follower_count") is not None:
            return {
                "handle": f"@{handle}",
                "name": profile.get("full_name", ""),
                "bio": profile.get("biography", ""),
                "followers": int(profile.get("follower_count", 0)),
                "following": int(profile.get("following_count", 0)),
                "posts": int(profile.get("post_count", 0)),
                "profile_pic": profile.get("profile_pic_url", ""),
                "user_id": profile.get("pk", ""),
                "source": "graphql",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        return None

    def _deep_search(self, obj, targets: dict) -> Optional[dict]:
        """
        Búsqueda recursiva profunda en JSON buscando los campos target.
        Retorna el primer objeto que contenga TODOS los campos target no-None.
        """
        if isinstance(obj, dict):
            # Verificar si este nodo contiene los datos buscados
            match = True
            for key in targets:
                if key not in obj:
                    match = False
                    break
            if match:
                # Verificar que al menos tenga datos numéricos relevantes
                if obj.get("follower_count") is not None:
                    return obj

            # Si no, seguir buscando
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    result = self._deep_search(value, targets)
                    if result:
                        return result

        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    result = self._deep_search(item, targets)
                    if result:
                        return result

        return None

    def _fallback_extract(self, handle: str) -> Optional[dict]:
        """
        Fallback: extrae datos de la página HTML directamente.
        Busca en meta tags, texto visible, y datos JSON-LD.
        """
        url = f"{self.BASE_URL}/@{handle}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Fallback fetch failed for @{handle}: {e}")
            return None

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

        # Meta tags OG
        og_title = soup.find("meta", property="og:title")
        if og_title:
            data["name"] = og_title.get("content", "")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            data["bio"] = og_desc.get("content", "")

        # Buscar seguidores en el texto visible
        patterns = [
            r'([\d,.KMkB]+)\s*(?:follower|seguidor)',
            r'([\d,.KMkB]+)\s*seguidores',
            r'([\d,.KMkB]+)\s*followers?',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count = self._parse_count(match.group(1))
                if count > 0:
                    data["followers"] = count
                    break

        # Buscar posts count
        post_patterns = [
            r'([\d,.KMkB]+)\s*(?:posts?|publicacion)',
            r'([\d,.KMkB]+)\s*publicaciones',
        ]
        for pattern in post_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["posts"] = self._parse_count(match.group(1))
                break

        # Buscar JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict):
                    if ld.get("name"):
                        data["name"] = ld.get("name", data["name"])
                    if ld.get("description"):
                        data["bio"] = ld.get("description", data["bio"])
            except (json.JSONDecodeError, AttributeError):
                continue

        return data

    @staticmethod
    def _parse_count(text) -> int:
        """Parsea strings como '1.2M', '500K', '1,234' a enteros."""
        if not text:
            return 0
        if isinstance(text, (int, float)):
            return int(text)

        text = str(text).strip().upper().replace(",", "")

        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        for suffix, multiplier in multipliers.items():
            if text.endswith(suffix):
                try:
                    return int(float(text.rstrip(suffix)) * multiplier)
                except ValueError:
                    return 0

        try:
            return int(float(text))
        except ValueError:
            return 0

    def close(self):
        self.client.close()


# ─── Conveniencia ───────────────────────────────────────────────

async def scrape_threads_profile(handle: str) -> Optional[dict]:
    """
    Scrapea un perfil de Threads. Ejecuta en thread pool para no bloquear.
    """
    loop = asyncio.get_event_loop()
    scraper = ThreadsScraper()
    try:
        result = await loop.run_in_executor(None, scraper.scrape_profile, handle)
        return result
    finally:
        scraper.close()


async def scrape_threads_posts(handle: str, limit: int = 10) -> list[dict]:
    """
    Scrapea posts recientes de un perfil de Threads (experimental).
    """
    loop = asyncio.get_event_loop()
    scraper = ThreadsScraper()
    try:
        clean_handle = handle.lstrip("@")
        user_id = await loop.run_in_executor(None, scraper._resolve_user_id, clean_handle)
        if not user_id:
            return []

        # Doc ID para posts del perfil
        POSTS_DOC_ID = "6232751443445612"
        variables = json.dumps({"userID": user_id})

        def fetch_posts():
            payload = {"doc_id": POSTS_DOC_ID, "variables": variables}
            try:
                resp = scraper.client.post(
                    scraper.GRAPHQL_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
            return None

        result = await loop.run_in_executor(None, fetch_posts)
        if not result:
            return []

        posts = []
        # Navegar estructura para encontrar threads
        def find_threads(obj, collected):
            if isinstance(obj, dict):
                if obj.get("threads") and isinstance(obj["threads"], list):
                    collected.extend(obj["threads"])
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        find_threads(v, collected)
            elif isinstance(obj, list):
                for item in obj:
                    find_threads(item, collected)

        all_threads = []
        find_threads(result, all_threads)

        for thread in all_threads[:limit]:
            thread_data = thread if isinstance(thread, dict) else {}
            posts.append({
                "post_id": str(thread_data.get("id", "")),
                "text": thread_data.get("text", thread_data.get("caption", "")),
                "likes": thread_data.get("like_count", thread_data.get("likes", 0)),
                "replies": thread_data.get("reply_count", thread_data.get("replies", 0)),
                "reposts": thread_data.get("repost_count", thread_data.get("reposts", 0)),
                "has_image": bool(thread_data.get("image_urls") or thread_data.get("has_image")),
                "has_video": bool(thread_data.get("video_url") or thread_data.get("has_video")),
                "taken_at": thread_data.get("taken_at", None),
            })

        return posts
    finally:
        scraper.close()
