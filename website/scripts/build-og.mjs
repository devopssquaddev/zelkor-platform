// Social preview cards (og:image) for docs.zelkor.io. LinkedIn and X do not run Mermaid, so each
// page with a diagram gets a 1200x630 PNG: title on the left, its first diagram on the right.
// Pages without one share og/default.png. PNGs are committed; the site build never runs Chrome.
//
// Usage (from website/):
//   npm run og          re-render stale cards with a local Chrome (CHROME_PATH overrides the path)
//   npm run og -- --all re-render every card
//   npm run og:check    fail if a card is stale or missing (CI; no Chrome)
//
// Frontmatter: `og_diagram: 2` picks the second diagram; `og_diagram: none` uses the default card.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

const here = path.dirname(fileURLToPath(import.meta.url));
const websiteDir = path.resolve(here, '..');
const docsDir = path.resolve(websiteDir, '../docs');
const outDir = path.join(docsDir, 'public/og');
const manifestPath = path.join(websiteDir, 'og-manifest.json');
const W = 1200;
const H = 630;

function listMarkdown(dir, out = []) {
  for (const name of fs.readdirSync(dir).sort()) {
    const abs = path.join(dir, name);
    if (name === 'public') {
      continue;
    }
    if (fs.statSync(abs).isDirectory()) {
      listMarkdown(abs, out);
    } else if (name.endsWith('.md')) {
      out.push(abs);
    }
  }
  return out;
}

// Root README.md is rewritten to index.md (config.mts); nested README.md keeps its name.
export function pageSlug(relativePath) {
  const rel = relativePath.replace(/\\/g, '/');
  return rel === 'README.md' || rel === 'index.md' ? 'index' : rel.replace(/\.md$/, '');
}

function mermaidBlocks(body) {
  return [...body.matchAll(/^```mermaid\n([\s\S]*?)^```/gm)].map((m) => m[1]);
}

function collectCards() {
  const cards = [{ slug: 'default', kind: 'default' }];
  for (const file of listMarkdown(docsDir)) {
    const rel = path.relative(docsDir, file);
    const { data, content } = matter(fs.readFileSync(file, 'utf8'));
    const diagrams = mermaidBlocks(content);
    const pick = data.og_diagram ?? 1;
    if (pick === 'none' || diagrams.length === 0) {
      continue;
    }
    if (!Number.isInteger(pick) || pick < 1 || pick > diagrams.length) {
      throw new Error(`${rel}: og_diagram must be 1..${diagrams.length} or none, got ${JSON.stringify(pick)}`);
    }
    cards.push({
      slug: pageSlug(rel),
      kind: 'diagram',
      group: data.sidebar_group || '',
      title: String(data.title),
      description: String(data.description || ''),
      diagram: diagrams[pick - 1],
    });
  }
  const self = fs.readFileSync(fileURLToPath(import.meta.url), 'utf8') + fs.readFileSync(path.join(here, 'og-logo.svg'), 'utf8');
  for (const card of cards) {
    card.hash = crypto.createHash('sha256').update(self).update(JSON.stringify(card)).digest('hex').slice(0, 16);
  }
  return cards;
}

const pngPath = (slug) => path.join(outDir, `${slug}.png`);

function staleCards(cards, manifest) {
  return cards.filter((c) => manifest[c.slug] !== c.hash || !fs.existsSync(pngPath(c.slug)));
}

const esc = (s) => s.replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]);

function fontFace(file, weight) {
  const b64 = fs.readFileSync(path.join(websiteDir, 'node_modules/vitepress/dist/client/theme-default/fonts', file)).toString('base64');
  return `@font-face{font-family:Inter;font-weight:${weight};src:url(data:font/woff2;base64,${b64}) format('woff2')}`;
}

const logo = fs.readFileSync(path.join(here, 'og-logo.svg'), 'utf8');

function cardHtml(card) {
  const fonts = fontFace('inter-roman-latin.woff2', '100 900');
  const base = `${fonts}
    *{margin:0;box-sizing:border-box}
    body{width:${W}px;height:${H}px;background:#0B0F19;color:#F8FAFC;font-family:Inter,sans-serif;overflow:hidden}
    .foot{position:absolute;left:64px;bottom:52px;display:flex;align-items:center;gap:16px;font-size:24px;color:#CBD5E1}
    .foot svg{width:44px;height:44px}
    .foot b{color:#F8FAFC;font-weight:700}
    .bar{position:absolute;left:0;top:0;width:100%;height:8px;background:#3B82F6}`;
  if (card.kind === 'default') {
    return `<style>${base}
      .main{position:absolute;left:64px;top:150px;width:1060px}
      .main h1{font-size:76px;line-height:1.08;font-weight:800;letter-spacing:-1.5px}
      .main p{margin-top:30px;font-size:32px;line-height:1.4;color:#CBD5E1}
      .tags{margin-top:30px;display:flex;gap:14px}
      .tags span{font-size:22px;padding:8px 16px;border:2px solid #334155;border-radius:999px;color:#E2E8F0}
    </style><div class="bar"></div><div class="main">
      <h1>The self-hosted agent runtime</h1>
      <p>Bring the agent you already wrote. Zelkor runs it on your Kubernetes, armored.</p>
      <div class="tags"><span>Sandboxed</span><span>Verified prompts</span><span>Budgets</span><span>Traced</span><span>Tenant-isolated</span></div>
    </div><div class="foot">${logo}<span><b>Zelkor</b> · docs.zelkor.io</span></div>`;
  }
  return `<style>${base}
    .text{position:absolute;left:64px;top:84px;width:440px}
    .group{font-size:22px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#60A5FA}
    .text h1{margin-top:18px;font-size:52px;line-height:1.1;font-weight:800;letter-spacing:-1px;
       display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
    .text p{margin-top:22px;font-size:25px;line-height:1.4;color:#CBD5E1;
      display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
    .panel{position:absolute;left:556px;top:48px;width:596px;height:534px;background:#FFFFFF;color:#1F2937;border-radius:18px;
           display:flex;align-items:center;justify-content:center;padding:24px}
    #d{display:flex;align-items:center;justify-content:center;width:100%;height:100%}
    /* Wide diagrams (flowchart LR, long sequences): title on top, diagram across the card. */
    .wide .text{top:52px;width:1072px}
    .wide .text h1{font-size:46px;-webkit-line-clamp:2}
    .wide .text p{display:none}
    .wide .panel{left:64px;top:196px;width:1072px;height:320px}
  </style><div class="bar"></div><div class="text">
    <div class="group">${esc(card.group)}</div><h1>${esc(card.title)}</h1><p>${esc(card.description)}</p>
  </div><div class="panel"><div id="d"></div></div>
  <div class="foot">${logo}<span><b>Zelkor</b> · docs.zelkor.io</span></div>`;
}

function chromePath() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) {
    throw new Error('no Chrome found; set CHROME_PATH');
  }
  return found;
}

async function render(cards) {
  const { default: puppeteer } = await import('puppeteer-core');
  const browser = await puppeteer.launch({ executablePath: chromePath(), headless: true, args: ['--no-sandbox'] });
  try {
    for (const card of cards) {
      const page = await browser.newPage();
      await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
      await page.setContent(cardHtml(card), { waitUntil: 'load' });
      if (card.kind === 'diagram') {
        await page.addScriptTag({ path: path.join(websiteDir, 'node_modules/mermaid/dist/mermaid.min.js') });
        await page.evaluate(async (src) => {
          const mermaid = window.mermaid;
          mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', fontFamily: 'Inter, sans-serif' });
          const { svg } = await mermaid.render('og', src);
          const box = document.getElementById('d');
          box.innerHTML = svg;
          const el = box.querySelector('svg');
          const vb = el.viewBox.baseVal;
          const fit = () => Math.min(box.clientWidth / vb.width, box.clientHeight / vb.height, 2);
          const side = fit();
          document.body.classList.add('wide');
          if (fit() < side * 1.25) {
            document.body.classList.remove('wide');
          }
          const scale = fit();
          el.removeAttribute('style');
          el.setAttribute('width', String(vb.width * scale));
          el.setAttribute('height', String(vb.height * scale));
        }, card.diagram);
      }
      await page.evaluate(() => document.fonts.ready);
      fs.mkdirSync(path.dirname(pngPath(card.slug)), { recursive: true });
      await page.screenshot({ path: pngPath(card.slug), type: 'png' });
      await page.close();
      console.log(`og: ${card.slug}.png`);
    }
  } finally {
    await browser.close();
  }
}

function removeOrphans(cards) {
  const keep = new Set(cards.map((c) => pngPath(c.slug)));
  const walk = (dir) => {
    for (const name of fs.existsSync(dir) ? fs.readdirSync(dir) : []) {
      const abs = path.join(dir, name);
      if (fs.statSync(abs).isDirectory()) {
        walk(abs);
      } else if (name.endsWith('.png') && !keep.has(abs)) {
        fs.rmSync(abs);
        console.log(`og: removed ${path.relative(outDir, abs)}`);
      }
    }
  };
  walk(outDir);
}

async function main() {
  const args = new Set(process.argv.slice(2));
  const cards = collectCards();
  const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};
  const stale = args.has('--all') ? cards : staleCards(cards, manifest);
  const orphans = Object.keys(manifest).filter((slug) => !cards.some((c) => c.slug === slug));

  if (args.has('--check')) {
    if (stale.length || orphans.length) {
      console.error(`og cards out of date: ${[...stale.map((c) => c.slug), ...orphans].join(', ')}`);
      console.error('run `npm run og` in website/ and commit docs/public/og and website/og-manifest.json');
      process.exit(1);
    }
    console.log(`og: ${cards.length} cards up to date`);
    return;
  }

  await render(stale);
  removeOrphans(cards);
  const next = Object.fromEntries(cards.map((c) => [c.slug, c.hash]));
  fs.writeFileSync(manifestPath, JSON.stringify(next, null, 2) + '\n');
  console.log(`og: ${stale.length} rendered, ${cards.length} total`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await main();
}
