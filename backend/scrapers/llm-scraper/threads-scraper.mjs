#!/usr/bin/env node
/**
 * Threads LLM Scraper — Extracción potenciada por LLM.
 *
 * Usa llm-scraper + Playwright + LLM (OpenAI/Groq/Ollama) para extraer
 * datos estructurados de perfiles de Threads de forma inteligente.
 *
 * Uso:
 *   node threads-scraper.mjs <handle> [--provider openai|groq|ollama] [--posts]
 *
 * Ejemplo:
 *   node threads-scraper.mjs elespectador --provider groq
 *   node threads-scraper.mjs clarin --posts --provider groq
 *
 * La salida es JSON por stdout para que Python lo consuma via subprocess.
 */

import { chromium } from 'playwright';
import LLMScraper from 'llm-scraper';
import { z } from 'zod';
import { createOpenAI } from '@ai-sdk/openai';
import { Output } from 'ai';

// ─── Configuración ──────────────────────────────────────────────

const GROQ_BASE_URL = 'https://api.groq.com/openai/v1';

const PROVIDER_CONFIGS = {
  openai: () => {
    const apiKey = process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;
    if (!apiKey) throw new Error('Falta OPENAI_API_KEY o LLM_API_KEY');
    return createOpenAI({ apiKey })('gpt-4o-mini');
  },
  groq: () => {
    const apiKey = process.env.GROQ_API_KEY || process.env.LLM_API_KEY;
    if (!apiKey) throw new Error('Falta GROQ_API_KEY para usar Groq (gratis)');
    return createOpenAI({ baseURL: GROQ_BASE_URL, apiKey })('llama-3.3-70b-versatile');
  },
  openai_large: () => {
    const apiKey = process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;
    if (!apiKey) throw new Error('Falta OPENAI_API_KEY');
    return createOpenAI({ apiKey })('gpt-4o');
  },
};

// ─── Schemas Zod ────────────────────────────────────────────────

const ProfileSchema = z.object({
  profile: z.object({
    handle: z.string().describe('The Threads handle (username) without @'),
    name: z.string().describe('Full display name of the account'),
    bio: z.string().nullable().describe('Biography/description text'),
    followers: z.number().describe('Total follower count'),
    following: z.number().describe('Total following count'),
    posts: z.number().describe('Total number of posts/threads'),
    profile_pic_url: z.string().nullable().describe('URL of profile picture'),
    is_verified: z.boolean().default(false).describe('Whether the account is verified'),
  }).describe('The Threads profile information'),
});

const PostsSchema = z.object({
  posts: z.array(z.object({
    post_id: z.string().describe('Unique ID of the post'),
    text: z.string().describe('Text content of the post'),
    likes: z.number().describe('Number of likes'),
    replies: z.number().describe('Number of replies/comments'),
    reposts: z.number().describe('Number of reposts/quotes'),
    views: z.number().optional().describe('Number of views if available'),
    has_image: z.boolean().describe('Whether the post has images'),
    has_video: z.boolean().describe('Whether the post has a video'),
    posted_at: z.string().nullable().describe('ISO timestamp of when the post was made'),
    permalink: z.string().nullable().describe('URL to the post'),
  })).describe('Recent posts from the profile'),
});

const FullProfileSchema = z.object({
  profile: z.object({
    handle: z.string(),
    name: z.string(),
    bio: z.string().nullable(),
    followers: z.number(),
    following: z.number(),
    posts: z.number(),
    profile_pic_url: z.string().nullable(),
    is_verified: z.boolean().default(false),
  }),
  posts: z.array(z.object({
    post_id: z.string(),
    text: z.string(),
    likes: z.number(),
    replies: z.number(),
    reposts: z.number(),
    views: z.number().optional(),
    has_image: z.boolean(),
    has_video: z.boolean(),
    posted_at: z.string().nullable(),
    permalink: z.string().nullable(),
  })).optional(),
});

// ─── Scraper ────────────────────────────────────────────────────

async function scrapeThreadsProfile(handle, options = {}) {
  const { includePosts = false, provider = 'groq', format = 'html' } = options;
  const cleanHandle = handle.replace('@', '');
  const url = `https://www.threads.com/@${cleanHandle}`;

  // Inicializar LLM provider
  const providerFn = PROVIDER_CONFIGS[provider];
  if (!providerFn) {
    return { status: 'error', error: `Provider desconocido: ${provider}. Usa: ${Object.keys(PROVIDER_CONFIGS).join(', ')}` };
  }

  let llm;
  try {
    llm = providerFn();
  } catch (err) {
    console.error(`⚠️ Error en provider ${provider}: ${err.message}`);
    return { status: 'no_key', error: err.message, provider };
  }

  // Inicializar Playwright
  console.error(`🚀 Lanzando Chromium via Playwright (llm-scraper)...`);
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1920,1080',
    ],
  });

  const page = await browser.newPage({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
    locale: 'es-CO',
  });

  // Anti-detección
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['es-CO', 'es', 'en-US'] });
    window.chrome = {
      runtime: {},
      loadTimes: () => ({ startLoadTime: Date.now() / 1000 }),
      csi: () => ({ startE: Date.now() }),
    };
  });

  try {
    // Navegar al perfil
    console.error(`🌐 Navegando a ${url}...`);
    const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

    // Verificar login redirect
    if (page.url().includes('/login')) {
      // Si nos redirigieron al login, intentar con screenshot (multimodal)
      console.error('⚠️ Página redirigió a login, intentando con screenshot...');
      
      if (format === 'image') {
        // Ya estamos en modo imagen, intentar de todas formas
      } else {
        // Reintentar con formato image (screenshot para multimodal)
        browser.close();
        return await scrapeThreadsProfile(handle, { ...options, format: 'image' });
      }
    }

    await page.waitForTimeout(3000);

    // Crear scraper
    const scraper = new LLMScraper(llm);

    const schema = includePosts ? FullProfileSchema : ProfileSchema;

    console.error(`🤖 Ejecutando LLM Scraper (provider: ${provider}, format: ${format})...`);

    let result;
    
    if (format === 'image') {
      // Modo screenshot — requiere modelo multimodal (GPT-4o, Gemini, etc.)
      result = await scraper.run(page, Output.object({ schema }), { 
        format: 'image',
        instruction: `Extract the Threads profile information from this screenshot of ${url}. Include follower count, following count, post count, name, and bio.`,
      });
    } else {
      // Modo HTML — el LLM analiza el HTML renderizado
      result = await scraper.run(page, Output.object({ schema }), { 
        format: 'html',
      });
    }

    const data = result.data;

    // Si también queremos posts y no los incluimos aún
    if (includePosts && !data.posts && format !== 'image') {
      console.error('📝 Extrayendo posts adicionales...');
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(2000);
      
      const postsResult = await scraper.run(page, Output.object({ schema: PostsSchema }), {
        format: 'html',
      });
      
      data.posts = postsResult.data?.posts || [];
    }

    return {
      status: 'ok',
      source: `llm_scraper_${format}`,
      provider,
      data,
      scraped_at: new Date().toISOString(),
    };

  } catch (error) {
    // Si falló con HTML, intentar con screenshot si no lo hicimos ya
    if (format !== 'image') {
      console.error(`⚠️ Error con formato ${format}: ${error.message}. Reintentando con screenshot...`);
      try {
        await browser.close();
        return await scrapeThreadsProfile(handle, { ...options, format: 'image' });
      } catch (retryError) {
        return {
          status: 'error',
          error: `Error con HTML y con imagen: ${error.message} | ${retryError.message}`,
        };
      }
    }
    
    return {
      status: 'error',
      error: error.message,
      stack: error.stack,
    };
  } finally {
    await browser.close();
  }
}

// ─── Main ───────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const handle = args.find(a => !a.startsWith('--'));
  const provider = args.includes('--provider') 
    ? args[args.indexOf('--provider') + 1] 
    : (process.env.LLM_PROVIDER || 'groq');
  const includePosts = args.includes('--posts');

  if (!handle) {
    console.error('Uso: node threads-scraper.mjs <handle> [--provider openai|groq] [--posts]');
    console.error('Ej:  node threads-scraper.mjs elespectador --provider groq');
    process.exit(1);
  }

  const result = await scrapeThreadsProfile(handle, { includePosts, provider });
  
  // Salida JSON para que Python lo consuma
  console.log(JSON.stringify(result, null, 2));
}

main().catch(err => {
  console.error(JSON.stringify({ status: 'error', error: err.message }));
  process.exit(1);
});
