# Zelkor site

Marketing site. Docs stay in `website/` and are not built here.

A 6-variant switcher in the top bar toggles theme and copy (Cobalt, Obsidian, Swiss, Signal, Emerald, Emerald Defense). Default is Variant 6.

## Local

```bash
cd site
npm ci
npm run dev
```

`npm run build` writes `site/.vitepress/dist`.

## Cloudflare (Workers Git)

Project name in the dashboard must be `zelkor-site` (same as `name` in `wrangler.toml`).

| Field | Value |
| :--- | :--- |
| Root directory | `site` |
| Build command | `npm ci && npm run build` |
| Deploy command | `npx wrangler deploy` |
| Node | `22` |

Docs, GitHub, and the architecture-review form URLs are constants in `.vitepress/links.ts`.
