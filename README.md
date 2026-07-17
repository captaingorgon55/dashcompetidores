# 🏆 Competitor Dashboard

**Monitoreo en vivo de competidores para El Espectador & Revista VEA**

Dashboard web para analizar y comparar métricas de Threads, Google Discover, Search Engines y News Aggregators con inteligencia artificial.

---

## 🚀 Stack

- **Backend:** Python + FastAPI + SQLAlchemy (async)
- **Frontend:** HTML + CSS + JavaScript + Chart.js
- **Base de datos:** SQLite
- **Scraping:** httpx + BeautifulSoup
- **APIs:** Google Search Console + Google Analytics Data API
- **Deploy:** Render.com

---

## 📦 Instalación Local

```bash
# 1. Clonar el repo
cd competitor-dashboard

# 2. Instalar dependencias
pip install -r backend/requirements.txt

# 3. Iniciar el servidor
python -m uvicorn backend.main:app --reload --port 8000

# 4. Abrir en el navegador
open http://localhost:8000
```

## 🌐 Deploy en Render

1. Conecta tu repositorio a Render
2. Render detectará automáticamente `render.yaml`
3. Configura las variables de entorno:
   - `GOOGLE_CLIENT_ID` — OAuth Client ID de Google
   - `GOOGLE_CLIENT_SECRET` — OAuth Client Secret de Google
   - `SITE_URL` — URL de tu site en Search Console (default: `sc-domain:elespectador.com`)

## 🔑 Configurar Google APIs

Para activar Search Console + Analytics:

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com)
2. Habilita:
   - Google Search Console API
   - Google Analytics Data API
3. Crea credenciales OAuth 2.0 con redirect URI `http://localhost:8000/auth/google/callback`
4. Configura las variables de entorno

## 📊 Páginas del Dashboard

| Página | Ruta | Descripción |
|--------|------|-------------|
| **Dashboard** | `/` | KPIs generales y comparativa |
| **Competidores** | `/competitors` | Lista con scrapeo manual |
| **Threads** | `/threads` | Evolución de seguidores |
| **Google Discover** | `/discover` | Impresiones, clics y CTR |
| **Search Traffic** | `/search` | Clics, impresiones y posición |
| **Entrada Manual** | `/manual-entry` | Datos de plataformas sin API |

## 🧠 Próximas Mejoras

- [ ] Autenticación OAuth2 con Google
- [ ] Scraping automático con scheduler
- [ ] Reportes PDF descargables
- [ ] Alertas de cambios significativos
- [ ] Más agregadores (Apple News, Flipboard, MSN)
- [ ] Análisis de sentimiento con IA
