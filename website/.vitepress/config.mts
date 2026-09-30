import { defineConfig } from 'vitepress';
import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const docsDir = path.resolve(__dirname, '../../docs');
const repoRoot = path.resolve(docsDir, '..');
const githubBlob = 'https://github.com/devopssquaddev/zelkor-platform/blob/main';
const preferredGroupOrder = [
  'Get started',
  'Architecture',
  'Install',
  'Agents',
  'Reference',
  'KB',
];

function listMarkdown(dir: string, out: string[] = []): string[] {
  for (const name of fs.readdirSync(dir)) {
    const abs = path.join(dir, name);
    if (fs.statSync(abs).isDirectory()) {
      listMarkdown(abs, out);
    } else if (name.endsWith('.md')) {
      out.push(abs);
    }
  }
  return out;
}

function pageLink(absFile: string): string {
  const rel = path.relative(docsDir, absFile).replace(/\\/g, '/');
  if (rel === 'README.md') {
    return '/';
  }
  return '/' + rel.replace(/\.md$/, '');
}

function buildSidebar() {
  const groups = new Map<string, { text: string; link: string; order: number }[]>();
  const missing: string[] = [];

  for (const file of listMarkdown(docsDir)) {
    const { data } = matter(fs.readFileSync(file, 'utf8'));
    const rel = path.relative(docsDir, file);
    if (!data.sidebar_group) {
      missing.push(rel);
      continue;
    }
    if (!groups.has(data.sidebar_group)) {
      groups.set(data.sidebar_group, []);
    }
    groups.get(data.sidebar_group)!.push({
      text: data.title || path.basename(file, '.md'),
      link: pageLink(file),
      order: Number(data.sidebar_order ?? 999),
    });
  }

  if (missing.length) {
    throw new Error(
      'docs page missing sidebar_group: ' + missing.sort().join(', '),
    );
  }

  const sidebar: { text: string; items: { text: string; link: string }[] }[] = [];
  const emit = (groupName: string) => {
    const items = groups.get(groupName);
    if (!items) {
      return;
    }
    items.sort((a, b) => a.order - b.order || a.text.localeCompare(b.text));
    sidebar.push({
      text: groupName,
      items: items.map(({ text, link }) => ({ text, link })),
    });
    groups.delete(groupName);
  };

  for (const name of preferredGroupOrder) {
    emit(name);
  }
  for (const name of [...groups.keys()].sort()) {
    emit(name);
  }
  return sidebar;
}

function rewriteOutOfTreeHref(href: string, relativePath: string): string {
  if (!href || /^(https?:|mailto:|tel:|#)/i.test(href)) {
    return href;
  }
  const hashIdx = href.indexOf('#');
  const pathname = hashIdx >= 0 ? href.slice(0, hashIdx) : href;
  const hash = hashIdx >= 0 ? href.slice(hashIdx) : '';
  if (!pathname) {
    return href;
  }
  const pageDir = path.dirname(path.join(docsDir, relativePath));
  const resolved = path.resolve(pageDir, pathname);
  const relToDocs = path.relative(docsDir, resolved);
  if (!relToDocs.startsWith('..') && !path.isAbsolute(relToDocs)) {
    return href;
  }
  const relToRepo = path.relative(repoRoot, resolved).replace(/\\/g, '/');
  return `${githubBlob}/${relToRepo}${hash}`;
}

function mermaidAndGithubMarkdown(md: {
  renderer: { rules: Record<string, ((...args: any[]) => string) | undefined> };
  utils: { escapeHtml: (s: string) => string };
  core: { ruler: { after: (before: string, name: string, fn: (state: any) => void) => void } };
}) {
  const fence = md.renderer.rules.fence;
  md.renderer.rules.fence = (tokens, idx, options, env, slf) => {
    const token = tokens[idx];
    if (token.info.trim().split(/\s+/)[0] === 'mermaid') {
      return `<pre class="mermaid">${md.utils.escapeHtml(token.content)}</pre>\n`;
    }
    return fence
      ? fence(tokens, idx, options, env, slf)
      : slf.renderToken(tokens, idx, options);
  };

  md.core.ruler.after('inline', 'zelkor-out-of-tree-github', (state) => {
    const relativePath = state.env?.relativePath || 'README.md';
    for (const block of state.tokens) {
      if (block.type !== 'inline' || !block.children) {
        continue;
      }
      for (const token of block.children) {
        if (token.type !== 'link_open') {
          continue;
        }
        const href = token.attrGet('href');
        if (!href) {
          continue;
        }
        token.attrSet('href', rewriteOutOfTreeHref(href, relativePath));
      }
    }
  });
}

export default defineConfig({
  title: 'Zelkor',
  description: 'Self-hosted runtime for AI agents on Kubernetes',
  srcDir: '../docs',
  rewrites: {
    'README.md': 'index.md',
  },
  ignoreDeadLinks: (url) => url.startsWith(githubBlob),
  appearance: false,
  markdown: {
    html: false,
    config: mermaidAndGithubMarkdown,
  },
  themeConfig: {
    sidebar: buildSidebar(),
    nav: [
      { text: 'Docs', link: '/' },
      { text: 'GitHub', link: 'https://github.com/devopssquaddev/zelkor-platform' },
    ],
    search: {
      provider: 'local',
    },
    outline: 'deep',
  },
  vite: {
    resolve: {
      alias: {
        vue: path.resolve(__dirname, '../node_modules/vue'),
        'vue/server-renderer': path.resolve(
          __dirname,
          '../node_modules/vue/server-renderer/index.mjs',
        ),
      },
    },
    ssr: {
      noExternal: ['mermaid'],
    },
  },
});
