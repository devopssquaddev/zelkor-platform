# Zelkor docs website

VitePress builds `../docs/` to static HTML. Cloudflare’s Git UI is **Workers Builds**: the Build command runs first on every branch, then `main` deploys and other branches run the Preview command. The output directory is **not** a dashboard field — it is `[assets].directory` in `wrangler.toml`.

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
2. Connect `zelkor-platform`, production branch `main`.
3. Settings:

| Field | Value |
| :--- | :--- |
| Root directory | `website` |
| Build command | `npm ci && npm run docs:build` |
| Preview command (non-production branches) | `npx wrangler preview` (needs the `[previews]` block in `wrangler.toml`) |
| API token | A **user** token (My Profile → API Tokens). If builds fail with `Authentication error [code: 10000]` / `Invalid access token [code: 9109]`, the stored token secret is stale: create a new one under Settings → Build → API token. |
| Node | `22` (`NODE_VERSION=22` if `.nvmrc` is ignored) |

There is no “build output” field. Wrangler uploads `.vitepress/dist` from `wrangler.toml`.
