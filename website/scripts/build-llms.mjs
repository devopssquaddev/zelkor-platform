// Build llms.txt (index), llms-full.txt (all docs) and one clean <page>.md per page into the
// built site, served at the root of docs.zelkor.io (llms.txt convention).
// Usage: node scripts/build-llms.mjs --out .vitepress/dist   (run by `npm run docs:build`)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

const here = path.dirname(fileURLToPath(import.meta.url));
const websiteDir = path.resolve(here, '..');
const docsDir = path.resolve(websiteDir, '../docs');
const repoRoot = path.resolve(docsDir, '..');
const siteBase = 'https://docs.zelkor.io/';
const maxIndexTokens = 2000;

const groups = [
  ['Get started', 'Get started'],
  ['Install', 'Install'],
  ['Agents', 'Deploy an agent'],
  ['Architecture', 'Architecture and threat model'],
  ['Reference', 'Reference (Helm values, CLI, MCP, providers)'],
  ['KB', 'Troubleshooting KB'],
];

// Canonical problem→solution pages: listed once, with the query they answer as the note.
export const lensQueries = {
  'agent-deploy.md': 'How to sandbox a LangGraph or CrewAI agent on Kubernetes: what stays in your image, what Zelkor injects',
  'architecture.md': 'Zelkor vs a DIY Kubernetes agent stack',
  'architecture-request-path.md': 'Keep OpenAI API keys out of Kubernetes pods; stop a runaway agent at the gateway',
  'architecture-sandbox.md': 'Isolate untrusted LLM-generated Python on Kubernetes (gVisor)',
  'architecture-trace.md': 'Trace every agent run in Langfuse',
  'architecture-tenants.md': 'Tenant isolation for AI agents and MCP tools on Kubernetes',
};

const proofMarker = /^\[\/\/\]: # \(zelkor-proof [a-z0-9-]+ (begin|end)\)\n?/gm;

function listMarkdown(dir, out = []) {
  for (const name of fs.readdirSync(dir).sort()) {
    const abs = path.join(dir, name);
    if (fs.statSync(abs).isDirectory()) {
      if (name !== 'public' && name !== 'assets') listMarkdown(abs, out);
    } else if (name.endsWith('.md')) {
      out.push(abs);
    }
  }
  return out;
}

function chartVersion() {
  const chart = fs.readFileSync(path.join(repoRoot, 'charts/zelkor-platform/Chart.yaml'), 'utf8');
  return chart.match(/^version:\s*"?([^"\s]+)"?/m)[1];
}

export function loadPages() {
  return listMarkdown(docsDir).map((abs) => {
    const { data, content } = matter(fs.readFileSync(abs, 'utf8'));
    const rel = path.relative(docsDir, abs).replace(/\\/g, '/');
    return {
      rel,
      title: data.title,
      description: data.description,
      group: data.sidebar_group,
      order: Number(data.sidebar_order ?? 999),
      body: content.replace(proofMarker, '').trim(),
    };
  });
}

function ordered(pages) {
  const rank = new Map(groups.map(([g], i) => [g, i]));
  return [...pages].sort(
    (a, b) =>
      (rank.get(a.group) ?? 99) - (rank.get(b.group) ?? 99) ||
      a.order - b.order ||
      a.title.localeCompare(b.title),
  );
}

export function buildIndex(pages) {
  const header = fs
    .readFileSync(path.join(websiteDir, 'llms-header.md'), 'utf8')
    .replaceAll('{{chartVersion}}', chartVersion())
    .trim();
  const lines = [header];
  for (const [group, heading] of groups) {
    const inGroup = ordered(pages).filter((p) => p.group === group && p.rel !== 'README.md');
    if (!inGroup.length) continue;
    lines.push('', `## ${heading}`, '');
    for (const p of inGroup) {
      lines.push(`- [${p.title}](${siteBase}${p.rel}): ${lensQueries[p.rel] ?? p.description}`);
    }
  }
  return lines.join('\n') + '\n';
}

export function buildFull(pages) {
  return (
    ordered(pages)
      .map((p) => `# ${p.title}\n\nSource: ${siteBase}${p.rel}\n\n${p.body.replace(/^# .*\n+/, '')}`)
      .join('\n\n---\n\n') + '\n'
  );
}

export function pageMarkdown(p) {
  return `# ${p.title}\n\n${p.body.replace(/^# .*\n+/, '')}\n`;
}

function main() {
  const outIdx = process.argv.indexOf('--out');
  if (outIdx < 0) throw new Error('usage: build-llms.mjs --out <dir>');
  const outDir = path.resolve(process.argv[outIdx + 1]);
  const pages = loadPages();
  const index = buildIndex(pages);
  const tokens = Math.ceil(index.length / 4);
  if (tokens > maxIndexTokens) {
    throw new Error(`llms.txt is ~${tokens} tokens; the limit is ${maxIndexTokens}. Shorten descriptions or the header.`);
  }
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'llms.txt'), index);
  fs.writeFileSync(path.join(outDir, 'llms-full.txt'), buildFull(pages));
  for (const p of pages) {
    if (p.rel === 'README.md') continue;
    fs.mkdirSync(path.dirname(path.join(outDir, p.rel)), { recursive: true });
    fs.writeFileSync(path.join(outDir, p.rel), pageMarkdown(p));
  }
  console.log(`llms.txt ~${tokens} tokens, ${pages.length} pages → ${outDir}`);
}

main();
