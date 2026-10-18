import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Zelkor',
  description:
    'Kubernetes runtime for LangGraph, LangChain, and Deep Agents. Zero upstream LLM keys in agent pods. Zelkor 2.3.2.',
  appearance: false,
  cleanUrls: true,
  srcExclude: ['README.md'],
  head: [
    ['link', { rel: 'icon', href: '/logo-mark.svg' }],
    [
      'script',
      {},
      `(function(){try{var v=localStorage.getItem('zelkor-site-variant-v6');var a=(!v||v==='6'||v==='v6')?'v6':(v>='1'&&v<='5'?v:'v6');document.documentElement.setAttribute('data-variant',a)}catch(e){document.documentElement.setAttribute('data-variant','v6')}})()`,
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
