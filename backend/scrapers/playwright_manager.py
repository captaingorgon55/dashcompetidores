"""
Playwright Browser Manager — Gestión eficiente del navegador headless.

Mantiene una única instancia de navegador reutilizable con contextos
aislados por perfil. Reduce la sobrecarga de lanzar Chromium cada vez.

Estrategias:
- Single browser instance, multiple contexts
- Context isolation per profile/user-agent
- Automatic cleanup on timeout
- Graceful shutdown
"""

import asyncio
import logging
import random
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from backend.config import (
    PLAYWRIGHT_HEADLESS, PLAYWRIGHT_TIMEOUT_MS,
    USER_AGENTS, PROXY_URL,
)

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """
    Singleton que gestiona el ciclo de vida del navegador Playwright.

    Uso:
        manager = PlaywrightManager()
        context = await manager.get_context()
        page = await context.new_page()
        await page.goto("https://threads.net")
        ...
        await manager.close()
    """

    _instance: Optional["PlaywrightManager"] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _contexts: dict[str, BrowserContext] = {}
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _ensure_browser(self):
        """Lanza el navegador si no existe. Thread-safe via lock."""
        async with self._lock:
            if self._browser is not None:
                return

            logger.info("🚀 Lanzando Chromium headless via Playwright...")
            self._playwright = await async_playwright().start()

            launch_options = {
                "headless": PLAYWRIGHT_HEADLESS,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-gpu",
                    "--window-size=1920,1080",
                ],
            }

            if PROXY_URL:
                launch_options["proxy"] = {"server": PROXY_URL}

            self._browser = await self._playwright.chromium.launch(**launch_options)
            logger.info("✅ Chromium listo")

    async def get_context(self, profile: str = "default") -> BrowserContext:
        """
        Obtiene (o crea) un contexto de navegador para un perfil específico.

        Cada perfil tiene su propio almacenamiento (cookies, localStorage)
        y User-Agent rotado. Útil para evitar detección por fingerprinting.
        """
        await self._ensure_browser()

        if profile in self._contexts:
            context = self._contexts[profile]
            # Verificar que el contexto siga vivo
            try:
                pages = context.pages
                return context
            except Exception:
                logger.warning(f"Contexto '{profile}' murió, creando uno nuevo")
                del self._contexts[profile]

        # Rotar User-Agent basado en el perfil (hash simple)
        ua_index = hash(profile) % len(USER_AGENTS)
        user_agent = USER_AGENTS[ua_index]

        context = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="es-CO",
            timezone_id="America/Bogota",
            extra_http_headers={
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        # Inyectar script para ocultar automatización
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-CO', 'es', 'en'] });
            // Chrome runtime
            window.chrome = { runtime: {} };
        """)

        self._contexts[profile] = context
        logger.debug(f"Contexto '{profile}' creado (UA: {user_agent[:50]}...)")
        return context

    async def close_context(self, profile: str = "default"):
        """Cierra un contexto específico."""
        if profile in self._contexts:
            try:
                await self._contexts[profile].close()
            except Exception:
                pass
            del self._contexts[profile]
            logger.debug(f"Contexto '{profile}' cerrado")

    async def close(self):
        """Cierra el navegador y Playwright completamente."""
        async with self._lock:
            for name, ctx in list(self._contexts.items()):
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._contexts.clear()

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            logger.info("👋 Navegador Playwright cerrado")


# Singleton global
playwright_manager = PlaywrightManager()
