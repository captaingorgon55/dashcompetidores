"""
Playwright Browser Manager — Gestión eficiente del navegador headless.

Soporta LD_LIBRARY_PATH automático (para servidores sin las librerías del
sistema instaladas globalmente). Configura la variable de entorno desde
~/.local/lib/chromium-deps/ si no está ya configurada.
"""

import asyncio
import logging
import os
from typing import Optional

# ─── LD_LIBRARY_PATH automático ───────────────────────────────
# En servidores sin sudo, las dependencias de Chromium se extraen
# a ~/.local/lib/chromium-deps/extracted/merged/
# Si LD_LIBRARY_PATH no está configurado pero las librerías existen,
# lo configuramos automáticamente.
_LD_LIBRARY_PATH_CONFIGURED = False
_CHROMIUM_DEPS = os.path.expanduser("~/.local/lib/chromium-deps/extracted/merged")

if not os.environ.get("LD_LIBRARY_PATH", ""):
    # Verificar si las librerías extraídas manualmente existen
    libnspr4 = os.path.join(_CHROMIUM_DEPS, "libnspr4.so")
    libnss3 = os.path.join(_CHROMIUM_DEPS, "libnss3.so")
    libasound = os.path.join(_CHROMIUM_DEPS, "libasound.so.2")
    if os.path.isfile(libnspr4) and os.path.isfile(libnss3) and os.path.isfile(libasound):
        os.environ["LD_LIBRARY_PATH"] = _CHROMIUM_DEPS
        _LD_LIBRARY_PATH_CONFIGURED = True

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from backend.config import (
    PLAYWRIGHT_HEADLESS,
    USER_AGENTS, PROXY_URL,
)

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """
    Singleton que gestiona el ciclo de vida del navegador Playwright.

    Auto-configura LD_LIBRARY_PATH si las librerías están en
    ~/.local/lib/chromium-deps/ (instalación manual sin sudo).
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

            if _LD_LIBRARY_PATH_CONFIGURED:
                logger.info(f"🔧 LD_LIBRARY_PATH configurado: {_CHROMIUM_DEPS}")

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

        # Inyectar script anti-detección avanzado
        # Basado en técnicas stealth para evitar fingerprinting de Meta/Threads
        await context.add_init_script("""
            // ─── Ocultar automatización ───
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = {
                runtime: {},
                loadTimes: function() {
                    return {
                        requestTime: Date.now() / 1000,
                        startLoadTime: Date.now() / 1000,
                        commitLoadTime: (Date.now() + 50) / 1000,
                        finishDocumentLoadTime: (Date.now() + 100) / 1000,
                        finishLoadTime: (Date.now() + 200) / 1000,
                        firstPaintTime: (Date.now() + 50) / 1000,
                        firstPaintAfterLoadTime: 0,
                        navigationType: 'other',
                        wasFetchedViaSpdy: true,
                        wasNpnNegotiated: false,
                        npnNegotiatedProtocol: 'h2',
                        wasAlternateProtocolAvailable: false,
                        connectionInfo: 'http/2',
                    };
                },
                csi: function() {
                    return {
                        startE: Date.now(),
                        onloadT: Date.now() + 200,
                        pageT: 'about:blank',
                        tran: Math.floor(Math.random() * 100),
                    };
                },
            };

            // ─── Plugins realistas ───
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', description: '', filename: 'internal-nacl-plugin' },
                ]
            });

            // ─── Lenguajes y localización ───
            Object.defineProperty(navigator, 'languages', { get: () => ['es-CO', 'es', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'language', { get: () => 'es-CO' });

            // ─── Hardware realista (evitar fingerprinting) ───
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

            // ─── Canvas fingerprinting (ruido mínimo) ───
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const result = originalToDataURL.call(this, type);
                return result;
            };

            // ─── WebGL fingerprinting (spoof renderer) ───
            try {
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(param) {
                    // Spoof UNMASKED_VENDOR/RENDERER_WEBGL
                    if (param === 37445) return 'Intel Inc.';
                    if (param === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter.call(this, param);
                };
            } catch(e) {}

            // ─── Permissions API ───
            try {
                if (navigator.permissions) {
                    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
                    navigator.permissions.query = (params) => {
                        if (params.name === 'notifications') {
                            return Promise.resolve({ state: 'prompt' });
                        }
                        return originalQuery(params);
                    };
                }
            } catch(e) {}

            // ─── Screen realista ───
            Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
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
