#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# setup_deps.sh — Instala dependencias del sistema para Chromium
#
# Chromium necesita: libnspr4, libnss3, libasound2
# Este script:
#   1. Detecta si las librerías están instaladas
#   2. Si no, intenta sudo apt-get install
#   3. Si no hay sudo, descarga los .deb y los extrae a ~/.local/lib/chromium-deps/
#   4. Crea run.sh con LD_LIBRARY_PATH para el servidor
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROMIUM_DEPS_DIR="${HOME}/.local/lib/chromium-deps"
EXTRACTED_DIR="${CHROMIUM_DEPS_DIR}/extracted/merged"
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Configuración de dependencias para Chromium${NC}"
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo ""

# ─── 1. Detectar qué librerías faltan ──────────────────────────

NEEDED_LIBS=("libnspr4.so" "libnss3.so" "libasound.so.2")
MISSING=()

echo -e "${YELLOW}🔍 Verificando librerías del sistema...${NC}"
for lib in "${NEEDED_LIBS[@]}"; do
    if ldconfig -p 2>/dev/null | grep -q "$lib"; then
        echo -e "  ✅ ${lib} — encontrada en el sistema"
    else
        echo -e "  ❌ ${lib} — NO encontrada"
        MISSING+=("$lib")
    fi
done

echo ""

# ─── 2. Resolver dependencias faltantes ───────────────────────

if [ ${#MISSING[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ Todas las librerías están instaladas en el sistema.${NC}"
    echo ""
    echo -e "${CYAN}Para iniciar el servidor:${NC}"
    echo -e "  cd ${SCRIPT_DIR} && python3 -m backend.main"
    echo ""
else
    echo -e "${YELLOW}⚠️  Faltan ${#MISSING[@]} librerías. Intentando instalar...${NC}"
    echo ""
    
    # Opción A: sudo apt-get install
    if sudo -n true 2>/dev/null; then
        echo -e "${GREEN}🔧 sudo disponible. Instalando paquetes...${NC}"
        sudo apt-get update -qq
        sudo apt-get install -y libnspr4 libnss3 libasound2
        echo -e "${GREEN}✅ Paquetes instalados.${NC}"
        
        # Verificar
        ALL_OK=true
        for lib in "${NEEDED_LIBS[@]}"; do
            if ! ldconfig -p 2>/dev/null | grep -q "$lib"; then
                echo -e "  ${RED}❌ ${lib} sigue faltando${NC}"
                ALL_OK=false
            fi
        done
        
        if $ALL_OK; then
            echo -e "${GREEN}✅ Todas las librerías instaladas correctamente.${NC}"
            echo ""
            echo -e "${CYAN}Para iniciar el servidor:${NC}"
            echo -e "  cd ${SCRIPT_DIR} && python3 -m backend.main"
            echo ""
            exit 0
        fi
        echo -e "${YELLOW}⚠️  Algunas librerías siguen faltando, usando fallback manual...${NC}"
    else
        echo -e "${YELLOW}⚠️  sudo no disponible. Usando instalación manual de .deb...${NC}"
    fi
    
    # ─── Opción B: Descargar .deb manualmente ────────────────
    echo ""
    echo -e "${YELLOW}📦 Descargando paquetes .deb...${NC}"
    mkdir -p "${CHROMIUM_DEPS_DIR}"
    cd "${CHROMIUM_DEPS_DIR}"
    
    # Eliminar .deb viejos si existen
    rm -f *.deb 2>/dev/null
    
    for pkg in libnspr4 libnss3 libasound2; do
        echo -n "  ${pkg}... "
        if apt-get download "$pkg" 2>/dev/null; then
            echo -e "${GREEN}✅${NC}"
        else
            echo -e "${RED}❌ falló${NC}"
        fi
    done
    
    # Extraer .deb
    echo ""
    echo -e "${YELLOW}📂 Extrayendo librerías...${NC}"
    mkdir -p "${EXTRACTED_DIR}"
    for deb in *.deb; do
        if [ -f "$deb" ]; then
            dpkg-deb -x "$deb" "${CHROMIUM_DEPS_DIR}/extracted" 2>/dev/null
            echo -e "  📦 ${deb} → extraído"
        fi
    done
    
    # Copiar todas las .so al directorio merged
    find "${CHROMIUM_DEPS_DIR}/extracted" -name "*.so*" -type f -exec cp -L {} "${EXTRACTED_DIR}/" \; 2>/dev/null
    
    # Crear symlinks faltantes
    cd "${EXTRACTED_DIR}"
    if [ -f "libasound.so.2.0.0" ] && [ ! -f "libasound.so.2" ]; then
        ln -sf libasound.so.2.0.0 libasound.so.2
    fi
    if [ -f "libasound.so.2" ] && [ ! -f "libasound.so" ]; then
        ln -sf libasound.so.2 libasound.so
    fi
    if [ -f "libnspr4.so" ] && [ ! -f "libnspr4.so.0d" ]; then
        ln -sf libnspr4.so libnspr4.so.0d
    fi
    
    echo ""
    echo -e "${GREEN}✅ Librerías extraídas en: ${EXTRACTED_DIR}${NC}"
    echo -e "   $(ls -1 *.so* 2>/dev/null | wc -l) archivos .so"
    
    # Verificar que las librerías clave existen
    MISSING_AFTER=()
    for lib in "${NEEDED_LIBS[@]}"; do
        if [ -f "${EXTRACTED_DIR}/${lib}" ]; then
            echo -e "  ✅ ${lib}"
        else
            echo -e "  ${RED}❌ ${lib} — no se pudo extraer${NC}"
            MISSING_AFTER+=("$lib")
        fi
    done
    
    if [ ${#MISSING_AFTER[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}❌ Error: No se pudieron obtener todas las librerías.${NC}"
        echo -e "   Faltan: ${MISSING_AFTER[*]}"
        echo -e "   Ejecuta manualmente: sudo apt-get install -y libnspr4 libnss3 libasound2"
        exit 1
    fi
    
    # ─── 3. Crear run.sh ────────────────────────────────────
    echo ""
    echo -e "${YELLOW}📝 Creando script run.sh...${NC}"
    
    cat > "${RUN_SCRIPT}" << 'RUNEOF'
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# run.sh — Inicia el servidor con LD_LIBRARY_PATH para Chromium
#
# Se configura automáticamente si las librerías del sistema
# no están disponibles.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS_DIR="${HOME}/.local/lib/chromium-deps/extracted/merged"

# Verificar si las librerías están en el sistema
if ldconfig -p 2>/dev/null | grep -q "libnspr4.so"; then
    echo "✅ Usando librerías del sistema"
    cd "${SCRIPT_DIR}"
    exec python3 -m backend.main
fi

# Si no, usar las extraídas manualmente
if [ -f "${DEPS_DIR}/libnspr4.so" ] && [ -f "${DEPS_DIR}/libnss3.so" ] && [ -f "${DEPS_DIR}/libasound.so.2" ]; then
    echo "✅ Usando librerías locales: ${DEPS_DIR}"
    export LD_LIBRARY_PATH="${DEPS_DIR}:${LD_LIBRARY_PATH:-}"
    cd "${SCRIPT_DIR}"
    exec python3 -m backend.main
fi

echo "❌ No se encontraron librerías para Chromium."
echo "   Ejecuta: bash setup_deps.sh"
echo "   O: sudo apt-get install -y libnspr4 libnss3 libasound2"
exit 1
RUNEOF
    
    chmod +x "${RUN_SCRIPT}"
    echo -e "${GREEN}✅ run.sh creado: ${RUN_SCRIPT}${NC}"
    
    # Verificar que Chromium funciona
    echo ""
    echo -e "${YELLOW}🔧 Verificando que Chromium funciona...${NC}"
    CHROME_PATH=$(find ~/.cache/ms-playwright -name "chrome-headless-shell" -type f 2>/dev/null | head -1)
    if [ -n "$CHROME_PATH" ]; then
        LD_LIBRARY_PATH="${EXTRACTED_DIR}" "$CHROME_PATH" --version 2>&1 && \
            echo -e "${GREEN}✅ Chromium funciona correctamente${NC}" || \
            echo -e "${RED}❌ Chromium no funciona${NC}"
    else
        echo -e "${YELLOW}⚠️  No se encontró Chromium. Debes instalarlo:${NC}"
        echo -e "   cd backend/scrapers/llm-scraper"
        echo -e "   npm run install-browser"
    fi
    
    echo ""
    echo -e "${CYAN}══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ Configuración completada.${NC}"
    echo ""
    echo -e "${CYAN}Para iniciar el servidor:${NC}"
    echo -e "  bash ${RUN_SCRIPT}"
    echo ""
    echo -e "${CYAN}O con las variables manualmente:${NC}"
    echo -e "  export LD_LIBRARY_PATH=\"${EXTRACTED_DIR}:\$LD_LIBRARY_PATH\""
    echo -e "  cd ${SCRIPT_DIR} && python3 -m backend.main"
    echo ""
fi
