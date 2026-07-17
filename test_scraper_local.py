#!/usr/bin/env python3
"""
🧪 Test Local Completo — ThreadsScraperPremium

Prueba todas las estrategias del scraper en vivo contra threads.com.
Uso:
    python3 test_scraper_local.py                    # modo completo
    python3 test_scraper_local.py --handle @elespectador  # perfil específico
    python3 test_scraper_local.py --quick            # solo estrategias principales
    python3 test_scraper_local.py --llm              # incluir LLM Scraper (requiere API key)
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_local")


# ─── Test de import ─────────────────────────────────────────────

def test_imports():
    """Verifica que todos los módulos importan correctamente."""
    print("\n" + "=" * 60)
    print("📦 1. IMPORTACIÓN DE MÓDULOS")
    print("=" * 60)
    errors = []

    try:
        from backend.config import (
            BASE_DIR, USER_AGENTS, DEFAULT_COMPETITORS,
            LLM_PROVIDER, META_ACCESS_TOKEN,
        )
        print(f"   ✅ config.py — {len(DEFAULT_COMPETITORS)} competidores, "
              f"{len(USER_AGENTS)} user agents")
        print(f"   📋 Referentes configurados:")
        for slug, d in DEFAULT_COMPETITORS.items():
            icon = "🔵" if d["is_us"] else "⚪"
            print(f"      {icon} {d['name']:25s} → {d['threads_handle']}")
        META_ACCESS_TOKEN = META_ACCESS_TOKEN
    except Exception as e:
        errors.append(f"config.py: {e}")
        META_ACCESS_TOKEN = None

    try:
        from backend.scrapers.llm_scraper_bridge import (
            llm_scrape_profile, PROVIDER_KEY_ENV
        )
        has_key = any(os.environ.get(env) for env in PROVIDER_KEY_ENV.get(LLM_PROVIDER, []))
        key_status = "✅ Configurada" if has_key else "❌ No configurada (gratis en console.groq.com)"
        print(f"   ✅ llm_scraper_bridge.py — {LLM_PROVIDER}: {key_status}")
    except Exception as e:
        errors.append(f"llm_scraper_bridge.py: {e}")

    try:
        from backend.scrapers.threads import (
            ThreadsScraperPremium, scrape_threads_profile,
            PLAYWRIGHT_AVAILABLE
        )
        pw_status = "✅ DISPONIBLE" if PLAYWRIGHT_AVAILABLE else "ℹ️ NO DISPONIBLE (usa llm-scraper)"
        print(f"   ✅ threads.py — Playwright: {pw_status}")
    except Exception as e:
        errors.append(f"threads.py: {e}")

    if errors:
        print(f"\n   ❌ Errores:")
        for e in errors:
            print(f"      • {e}")
        return False

    print(f"\n   ✅ Todos los módulos importados correctamente")
    return True


# ─── Test de scraper en vivo ────────────────────────────────────

async def test_scrape_profile(handle: str, use_llm: bool = False, quick: bool = False):
    """Prueba real de scrapeo contra threads.com."""
    print("\n" + "=" * 60)
    print(f"🔍 2. SCRAPEO EN VIVO — @{handle}")
    print("=" * 60)

    scraper = ThreadsScraperPremium()
    start = time.time()

    try:
        data = await scraper.scrape_profile(handle)
        elapsed = time.time() - start

        if data:
            print(f"\n   ✅ DATOS OBTENIDOS ({elapsed:.1f}s)")
            print(f"   ─────────────────────────────────")
            print(f"   Nombre:     {data.get('name', 'N/A')}")
            print(f"   Seguidores: {data.get('followers', 0):,}")
            print(f"   Siguiendo:  {data.get('following', 0):,}")
            print(f"   Posts:      {data.get('posts', 0):,}")
            print(f"   Bio:        {data.get('bio', '')[:100]}")
            print(f"   Verified:   {'✅' if data.get('is_verified') else '❌'}")
            print(f"   Fuente:     {data.get('source', 'N/A')}")
            print(f"   Handle:     {data.get('handle', 'N/A')}")
            return True
        else:
            print(f"\n   ❌ SIN DATOS ({elapsed:.1f}s)")
            print(f"   → threads.com podría estar bloqueando la IP")
            print(f"   → Soluciones:")
            print(f"      • Configura GROQ_API_KEY para activar llm-scraper")
            print(f"      • Usa un proxy (config.PROXY_URL)")
            print(f"      • Instala Playwright (pip install playwright)")
            return False

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n   ❌ ERROR ({elapsed:.1f}s): {e}")
        return False
    finally:
        scraper.close()


# ─── Test de warmup ────────────────────────────────────────────

async def test_warmup():
    """Ejecuta los mismos checks que hace el servidor al iniciar."""
    print("\n" + "=" * 60)
    print("🏁 3. WARMUP CHECKS — Diagnóstico del sistema")
    print("=" * 60)

    checks = []
    import shutil

    # Node.js
    node_path = shutil.which("node")
    if node_path:
        checks.append(("✅ Node.js", f"{node_path}"))
    else:
        checks.append(("❌ Node.js", "No encontrado en PATH"))

    # Node version
    if node_path:
        proc = await asyncio.create_subprocess_exec(
            "node", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        checks.append(("  Versión", stdout.decode().strip()))

    # npm packages
    if node_path:
        pkg_path = "backend/scrapers/llm-scraper/node_modules"
        if os.path.exists(pkg_path):
            pkgs = os.listdir(pkg_path)
            checks.append(("✅ npm modules", f"{len(pkgs)} paquetes instalados"))
        else:
            checks.append(("⚠️ npm modules", "No instalados. Ejecuta: cd backend/scrapers/llm-scraper && npm install"))

    # Playwright browser
    browser_path = os.path.expanduser("~/.cache/ms-playwright")
    if os.path.exists(browser_path):
        browsers = os.listdir(browser_path)
        checks.append(("✅ Playwright browsers", f"{len(browsers)} instalados"))
    else:
        checks.append(("⚠️ Playwright browsers", "No instalados. Ejecuta: npm run install-browser"))

    # Meta API
    from backend.config import META_ACCESS_TOKEN
    if META_ACCESS_TOKEN:
        checks.append(("✅ Meta API", "Token configurado"))
    else:
        checks.append(("ℹ️ Meta API", "Sin token (opcional)"))

    # LLM API keys
    from backend.config import LLM_PROVIDER
    from backend.scrapers.llm_scraper_bridge import PROVIDER_KEY_ENV
    required_envs = PROVIDER_KEY_ENV.get(LLM_PROVIDER, [])
    has_key = any(os.environ.get(env) for env in required_envs)
    if has_key:
        checks.append(("✅ LLM Scraper", f"{LLM_PROVIDER} configurado"))
    else:
        checks.append((
            "⚠️ LLM Scraper",
            f"Falta API key para {LLM_PROVIDER}. "
            f"Regístrate gratis: https://console.groq.com"
        ))

    # threads.com accesibilidad
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://www.threads.com/robots.txt")
            if resp.status_code == 200:
                checks.append(("✅ threads.com", "Responde correctamente"))
            else:
                checks.append(("⚠️ threads.com", f"Status: {resp.status_code}"))
    except Exception as e:
        checks.append(("❌ threads.com", f"No accesible: {e}"))

    # Mostrar resultados
    for name, detail in checks:
        icon = "✅" if name.startswith("✅") else ("⚠️" if name.startswith("⚠") or name.startswith("ℹ") else "❌")
        print(f"   {name:25s}  {detail}")

    return all(not name.startswith("❌") for name, _ in checks)


# ─── Test de LLM Scraper (requiere API key) ────────────────────

async def test_llm_scraper(handle: str):
    """Prueba el llm-scraper (Node.js) si hay API key."""
    print("\n" + "=" * 60)
    print("🤖 4. LLM SCRAPER (Node.js + Groq/OpenAI)")
    print("=" * 60)

    from backend.scrapers.llm_scraper_bridge import llm_scrape_profile, PROVIDER_KEY_ENV
    from backend.config import LLM_PROVIDER

    required_envs = PROVIDER_KEY_ENV.get(LLM_PROVIDER, [])
    has_key = any(os.environ.get(env) for env in required_envs)

    if not has_key:
        print(f"\n   ⏭️ Saltado — falta API key para {LLM_PROVIDER}")
        print(f"   Necesitas una de: {', '.join(required_envs)}")
        print(f"   Groq es gratis: https://console.groq.com")
        return False

    print(f"\n   🚀 Ejecutando con provider={LLM_PROVIDER}...")
    start = time.time()

    data = await llm_scrape_profile(
        handle,
        provider=LLM_PROVIDER,
        timeout=60,
    )

    elapsed = time.time() - start

    if data and data.get("followers", 0) > 0:
        print(f"\n   ✅ DATOS OBTENIDOS ({elapsed:.1f}s)")
        print(f"   Nombre:     {data.get('name', 'N/A')}")
        print(f"   Seguidores: {data.get('followers', 0):,}")
        print(f"   Siguiendo:  {data.get('following', 0):,}")
        print(f"   Posts:      {data.get('posts', 0):,}")
        print(f"   Fuente:     {data.get('source', 'N/A')}")
        return True
    else:
        print(f"\n   {'⚠️ Sin datos' if data else '❌ Falló'} ({elapsed:.1f}s)")
        return False


# ─── Main ───────────────────────────────────────────────────────

async def main():
    """Ejecuta todas las pruebas."""
    import argparse

    parser = argparse.ArgumentParser(description="Test completo del scraper de Threads")
    parser.add_argument("--handle", default="@elespectador",
                        help="Handle a testear (default: @elespectador)")
    parser.add_argument("--quick", action="store_true",
                        help="Solo pruebas rápidas (sin scrapeo en vivo)")
    parser.add_argument("--llm", action="store_true",
                        help="Incluir test de LLM Scraper")
    parser.add_argument("--output", type=str,
                        help="Guardar resultados en archivo JSON")
    args = parser.parse_args()

    clean_handle = args.handle.lstrip("@")
    results = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "handle": clean_handle, "tests": []}

    print("\n" + "█" * 60)
    print(f"  🧪 TEST LOCAL — ThreadsScraperPremium v3")
    print(f"  Handle: @{clean_handle}")
    print(f"  Fecha:  {results['timestamp']}")
    print("█" * 60)

    # 1. Imports
    imports_ok = test_imports()
    results["tests"].append({"name": "imports", "passed": imports_ok})

    if not imports_ok:
        print("\n❌ Los imports fallaron. Revisa las dependencias.")
        sys.exit(1)

    # 2. Warmup
    warmup_ok = await test_warmup()
    results["tests"].append({"name": "warmup", "passed": warmup_ok})

    # 3. Scrapeo en vivo (si no es modo quick)
    scrape_ok = None
    if not args.quick:
        scrape_ok = await test_scrape_profile(clean_handle)
        results["tests"].append({"name": "scrape_profile", "passed": scrape_ok})
    else:
        print("\n⏭️ Scrapeo en vivo saltado (modo --quick)")

    # 4. LLM Scraper (si se solicita)
    llm_ok = None
    if args.llm:
        llm_ok = await test_llm_scraper(clean_handle)
        results["tests"].append({"name": "llm_scraper", "passed": llm_ok})

    # ─── Resumen ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    for t in results["tests"]:
        status = "✅" if t["passed"] else ("⚠️" if t["passed"] is False else "⏭️")
        print(f"   {status} {t['name']}")

    # Guardar resultados
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n   📁 Resultados guardados en: {args.output}")

    # Consejos finales
    print(f"\n💡 PRÓXIMOS PASOS:")
    print(f"   1. Configura GROQ_API_KEY para activar llm-scraper (gratis)")
    print(f"      https://console.groq.com")
    if scrape_ok is False:
        print(f"   2. Si el scrapeo falló, instala Playwright en Python:")
        print(f"      pip install playwright && playwright install chromium")
    print(f"   3. Inicia el servidor:")
    print(f"      cd backend && uvicorn main:app --reload")
    print(f"   4. Abre el dashboard:")
    print(f"      http://localhost:8000")
    print()


if __name__ == "__main__":
    asyncio.run(main())
