"""
LLM Scraper Bridge — Puente Python → Node.js para usar llm-scraper.

Ejecuta el script Node.js como subproceso y parsea la salida JSON.
Esto nos permite usar la librería llm-scraper (TypeScript) desde
nuestro backend Python.

Estrategias:
1. Groq (gratis) — Llama 3.3 70B, tier gratuito (sin tarjeta)
2. OpenAI — GPT-4o-mini (rápido y barato)
3. Ollama — Local, completamente gratis

⚠️ Verifica automáticamente si hay API key antes de ejecutar Node.js.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# API key requirements por provider
PROVIDER_KEY_ENV = {
    "groq": ["GROQ_API_KEY", "LLM_API_KEY"],
    "openai": ["OPENAI_API_KEY", "LLM_API_KEY"],
    "openai_large": ["OPENAI_API_KEY", "LLM_API_KEY"],
}

# Ruta al proyecto Node.js
LLM_SCRAPER_DIR = Path(__file__).parent / "llm-scraper"
THREADS_SCRAPER_SCRIPT = LLM_SCRAPER_DIR / "threads-scraper.mjs"


async def llm_scrape_profile(
    handle: str,
    provider: str = "groq",
    include_posts: bool = False,
    timeout: int = 60,
) -> Optional[dict]:
    """
    Scrapea un perfil de Threads usando llm-scraper (Node.js).

    Args:
        handle: @handle o handle sin @
        provider: 'groq', 'openai', 'openai_large'
        include_posts: si incluir posts recientes
        timeout: timeout en segundos para el subprocess

    Returns:
        dict con datos del perfil o None si falla
    """
    clean_handle = handle.lstrip("@")

    # 1. Verificar que el script exista
    if not THREADS_SCRAPER_SCRIPT.exists():
        logger.error(f"❌ Script llm-scraper no encontrado: {THREADS_SCRAPER_SCRIPT}")
        return None

    # 2. Verificar API key antes de ejecutar Node.js
    required_envs = PROVIDER_KEY_ENV.get(provider, [])
    has_key = any(os.environ.get(env) for env in required_envs)
    if not has_key:
        logger.warning(f"⚠️ llm-scraper saltado para @{clean_handle}: falta API key para provider '{provider}'")
        logger.warning(f"   Necesitas una de: {', '.join(required_envs)}")
        return None

    # 3. Verificar que Node.js esté disponible
    import shutil
    node_path = shutil.which("node") or "node"

    cmd = [node_path, str(THREADS_SCRAPER_SCRIPT), clean_handle,
           "--provider", provider]

    if include_posts:
        cmd.append("--posts")

    logger.info(f"🤖 Ejecutando llm-scraper para @{clean_handle} (provider: {provider})...")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(LLM_SCRAPER_DIR),
            env={
                **os.environ,
                "LLM_PROVIDER": provider,
            },
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            logger.warning(f"⏱️ Timeout ({timeout}s) en llm-scraper para @{clean_handle}")
            return None

        # Log stderr (logs del scraper Node.js)
        stderr_text = stderr.decode().strip()
        if stderr_text:
            for line in stderr_text.split("\n"):
                logger.warning(f"  [llm-scraper] {line}")

        if process.returncode != 0:
            logger.warning(f"❌ llm-scraper exit code: {process.returncode} — stderr arriba ^")
            return None

        # Parsear JSON de salida
        try:
            result = json.loads(stdout.decode())
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando JSON de llm-scraper: {e}")
            logger.debug(f"   stdout: {stdout.decode()[:500]}")
            return None

        if result.get("status") in ("error", "no_key"):
            if result.get("status") == "no_key":
                logger.debug(f"⏭️ llm-scraper sin clave API para @{clean_handle}: {result.get('error', '')}")
            else:
                logger.warning(f"❌ llm-scraper error: {result.get('error', 'unknown')}")
            return None

        # Extraer datos en formato compatible con ThreadsScraperPremium
        data = result.get("data", {})
        profile = data.get("profile", {})
        posts = data.get("posts", [])

        output = {
            "handle": f"@{clean_handle}",
            "name": profile.get("name", ""),
            "bio": profile.get("bio", ""),
            "followers": int(profile.get("followers", 0)),
            "following": int(profile.get("following", 0)),
            "posts": int(profile.get("posts", 0)),
            "profile_pic": profile.get("profile_pic_url", ""),
            "is_verified": profile.get("is_verified", False),
            "source": f"llm_scraper_{result.get('source', provider)}",
            "scraped_at": result.get("scraped_at", ""),
            "llm_provider": result.get("provider", provider),
        }

        # Incluir posts si se pidieron
        if posts and include_posts:
            output["llm_posts"] = [
                {
                    "post_id": p.get("post_id", ""),
                    "text": p.get("text", ""),
                    "likes": int(p.get("likes", 0)),
                    "replies": int(p.get("replies", 0)),
                    "reposts": int(p.get("reposts", 0)),
                    "views": int(p.get("views", 0)) if p.get("views") else 0,
                    "has_image": p.get("has_image", False),
                    "has_video": p.get("has_video", False),
                    "posted_at": p.get("posted_at", None),
                    "permalink": p.get("permalink", ""),
                }
                for p in posts
            ]

        return output

    except FileNotFoundError:
        logger.error(f"❌ Node.js no encontrado en PATH: {node_path}")
        return None
    except Exception as e:
        logger.error(f"❌ Error ejecutando llm-scraper: {e}")
        return None


async def llm_scrape_posts(
    handle: str,
    provider: str = "groq",
    limit: int = 10,
    timeout: int = 60,
) -> list[dict]:
    """Scrapea posts recientes usando llm-scraper."""
    result = await llm_scrape_profile(
        handle,
        provider=provider,
        include_posts=True,
        timeout=timeout,
    )
    if result and "llm_posts" in result:
        return result["llm_posts"][:limit]
    return []
