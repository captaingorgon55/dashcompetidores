#!/usr/bin/env bash
set -euo pipefail

# ═════════════════════════════════════════════════════════════════
# 🧪 TEST LOCAL COMPLETO — Competitor Dashboard
#
# Instala dependencias, configura el entorno y ejecuta pruebas.
# Uso:
#   bash test_full.sh                    # modo normal
#   bash test_full.sh --llm              # con LLM Scraper
#   bash test_full.sh --quick            # solo imports + warmup
#   bash test_full.sh --handle @infobae  # perfil específico
# ═════════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
info()  { echo -e "${BLUE}[i]${NC} $1"; }
title() { echo -e "\n${BLUE}═══════════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════${NC}"; }

ARGS=()
HANDLE="@elespectador"
USE_LLM=false
QUICK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --llm) USE_LLM=true; shift ;;
        --quick) QUICK=true; shift ;;
        --handle) HANDLE="$2"; shift 2 ;;
        *) ARGS+=("$1"); shift ;;
    esac
done

START_TIME=$(date +%s)

# ═════════════════════════════════════════════════════════════════
# 1. VERIFICAR REQUISITOS
# ═════════════════════════════════════════════════════════════════

title "📋 1. VERIFICANDO REQUISITOS"

# Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    error "Python 3 no encontrado. Instálalo primero."
    exit 1
fi
log "Python: $($PYTHON --version 2>&1)"

# Node.js
if command -v node &>/dev/null; then
    log "Node.js: $(node --version)"
    log "npm: $(npm --version)"
else
    warn "Node.js no encontrado. El LLM Scraper no funcionará."
    warn "Instálalo: https://nodejs.org"
fi

# pip
if $PYTHON -m pip --version &>/dev/null; then
    log "pip: $($PYTHON -m pip --version 2>&1 | head -1)"
else
    error "pip no encontrado."
    exit 1
fi

# ═════════════════════════════════════════════════════════════════
# 2. CONFIGURAR ENTORNO
# ═════════════════════════════════════════════════════════════════

title "🔧 2. CONFIGURANDO ENTORNO"

# Crear .env si no existe
if [ ! -f backend/.env ]; then
    if [ -f backend/.env.example ]; then
        cp backend/.env.example backend/.env
        log ".env creado desde .env.example"
    else
        warn "No hay .env.example. Creando .env mínimo..."
        cat > backend/.env << 'EOF'
HOST=0.0.0.0
PORT=8000
DEBUG=true
LLM_PROVIDER=groq
THREADS_SCRAPE_INTERVAL_MINUTES=60
EOF
        log ".env mínimo creado"
    fi
else
    log ".env ya existe"
fi

# Crear directorio de datos
mkdir -p backend/data
log "Directorio backend/data/ listo"

# ═════════════════════════════════════════════════════════════════
# 3. INSTALAR DEPENDENCIAS PYTHON
# ═════════════════════════════════════════════════════════════════

title "🐍 3. INSTALANDO DEPENDENCIAS PYTHON"
info "Nota: Playwright NO se instala (ahorro ~300MB en servidores 512MB)"
info "      Para scraping con browser se usa llm-scraper (Node.js)"

$PYTHON -m pip install -r backend/requirements.txt --quiet 2>&1 | tail -5
log "Dependencias Python instaladas"

# ═════════════════════════════════════════════════════════════════
# 4. INSTALAR DEPENDENCIAS NODE.JS (LLM SCRAPER)
# ═════════════════════════════════════════════════════════════════

title "📦 4. INSTALANDO LLM-SCRAPER (NODE.JS)"

if command -v node &>/dev/null; then
    cd backend/scrapers/llm-scraper

    if [ -d node_modules ]; then
        log "node_modules ya existe"
    else
        info "Instalando dependencias npm (sin descargar Chromium aún)..."
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --silent 2>&1 | tail -3
        log "npm install completado"
    fi

    # Preguntar si instalar Chromium
    if [ ! -d ~/.cache/ms-playwright ] && [ "${CI:-}" != "true" ]; then
        warn ""
        warn "⚠️  Chromium headless shell NO está instalado (~150MB)"
        warn "   ¿Quieres descargarlo ahora para probar el LLM Scraper?"
        warn "   (npm run install-browser descargará ~150MB)"
        warn ""
        warn "   Responde:"
        warn "     s  → descargar ahora (recomendado)"
        warn "     n  → saltar (puedes hacerlo después con: npm run install-browser)"
        warn ""
        read -rp "   ¿Descargar? [s/N]: " -n 1 REPLY
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            info "Descargando chromium-headless-shell (~150MB)..."
            npm run install-browser 2>&1 | tail -5
            log "Chromium headless shell instalado"
        else
            warn "Chromium no descargado. El LLM Scraper no podrá lanzar el navegador."
            warn "Para instalarlo después: cd backend/scrapers/llm-scraper && npm run install-browser"
        fi
    elif [ -d ~/.cache/ms-playwright ]; then
        log "Chromium headless shell ya instalado"
    fi

    cd ../..
else
    warn "Saltando instalación Node.js (no disponible)"
fi

# ═════════════════════════════════════════════════════════════════
# 5. EJECUTAR PRUEBAS
# ═════════════════════════════════════════════════════════════════

title "🧪 5. EJECUTANDO PRUEBAS"

CMD="$PYTHON test_scraper_local.py --handle $HANDLE"
if $QUICK; then CMD="$CMD --quick"; fi
if $USE_LLM; then CMD="$CMD --llm"; fi

echo -e "${BLUE}   $ ${CMD}${NC}"
echo

$CMD

EXIT_CODE=$?

# ═════════════════════════════════════════════════════════════════
# 6. RESUMEN
# ═════════════════════════════════════════════════════════════════

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

title "📊 6. RESUMEN"
echo ""
echo "   ⏱️  Tiempo total: ${DURATION}s"
echo ""
echo "   📁 Archivos importantes:"
echo "      backend/.env            → Configuración"
echo "      backend/data/           → Base de datos SQLite"
echo "      backend/scrapers/llm-scraper/ → LLM Scraper (Node.js)"
echo ""
echo "   🚀 Para iniciar el servidor:"
echo "      cd backend && uvicorn main:app --reload"
echo "      → http://localhost:8000"
echo ""
echo "   🔑 Para activar Groq (gratis):"
echo "      1. Ve a https://console.groq.com"
echo "      2. Genera una API key"
echo "      3. Agrega al .env: GROQ_API_KEY=gsk_tu_key"
echo "      4. Vuelve a ejecutar: python3 test_scraper_local.py --llm"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "   ${GREEN}✅ PRUEBAS COMPLETADAS${NC}"
else
    echo -e "   ${RED}❌ ALGUNAS PRUEBAS FALLARON${NC}"
    echo -e "   ${YELLOW}   Revisa los mensajes arriba.${NC}"
    echo -e "   ${YELLOW}   Si es por bloqueo de threads.com, configura Groq.${NC}"
fi

exit $EXIT_CODE
