import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Zelkor — The self-hosted agent runtime',
  description:
    "The self-hosted agent runtime — bring the agent you already wrote; it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation; tenants stay isolated.",
  appearance: false,
  cleanUrls: true,
  srcExclude: ['README.md'],
  head: [
    ['link', { rel: 'icon', href: '/logo-mark.svg' }],
    [
      'script',
      {},
      `document.documentElement.setAttribute('data-variant','v7')`,
    ],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    [
      'link',
      { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    ],
    [
      'link',
      {
        rel: 'stylesheet',
        href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;900&family=Source+Serif+4:wght@600;700&display=swap',
      },
    ],
  ],
  themeConfig: {
    outline: false,
    sidebar: false,
  },
})
