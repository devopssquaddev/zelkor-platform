# Zelkor docs website

VitePress builds `../docs/` to static HTML for Cloudflare Pages.

Do **not** add `wrangler.toml` or run `npx wrangler deploy`.

## Local

```bash
cd website
npm ci
npm run docs:dev
```

- `npm run docs:build` writes `website/.vitepress/dist`
- `npm run docs:preview` serves that directory (`/`, `/quickstart`, `/architecture`, `/reference/helm-values`, `/kb/ai-gateway-vertex-unknown-backend`)

## Cloudflare Pages

Connect the **Pages** product (not Workers) to `zelkor-platform`. After the branch is on GitHub:

| Field | Value |
| :--- | :--- |
| Product | **Pages** (not Workers) |
| Repo | `zelkor-platform`, branch `main` (or this feature branch until merge) |
| Root directory | `website` |
| Build command | `npm ci && npm run docs:build` |
| Build output | `.vitepress/dist` |
| Deploy command | **empty** — not `npx wrangler deploy` |
| Node | `22` (`NODE_VERSION=22` if the dashboard does not pick up `.nvmrc`) |

Preview URL: `*.pages.dev`. Custom domain later on the same Pages project.
