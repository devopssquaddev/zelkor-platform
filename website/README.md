# Zelkor docs website

VitePress builds `../docs/` to static HTML. Cloudflare’s Git UI is **Workers Builds**: it always runs a deploy command. The output directory is **not** a dashboard field — it is `[assets].directory` in `wrangler.toml`.

## Local

```bash
cd website
npm ci
npm run docs:dev
```

- `npm run docs:build` writes `website/.vitepress/dist`
- `npm run docs:preview` serves that directory

## Cloudflare (Workers Git)

1. Project **name** in the dashboard must be exactly `zelkor-platform` (same as `name` in `wrangler.toml`).
2. Connect `zelkor-platform`, production branch `chore/docs-cleanup` until merge, then `main`.
3. Settings:

| Field | Value |
| :--- | :--- |
| Root directory | `website` |
| Build command | `npm ci && npm run docs:build` |
| Deploy command | `npx wrangler deploy` |
| Node | `22` (`NODE_VERSION=22` if `.nvmrc` is ignored) |

There is no “build output” field. Wrangler uploads `.vitepress/dist` from `wrangler.toml`.
