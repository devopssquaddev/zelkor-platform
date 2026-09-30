import DefaultTheme from 'vitepress/theme';
import type { Theme } from 'vitepress';
import { nextTick } from 'vue';

async function runMermaid() {
  await nextTick();
  const mermaid = (await import('mermaid')).default;
  // Do not set `theme` here — fences already declare `theme: neutral`.
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
  await mermaid.run({ querySelector: '.mermaid' });
}

export default {
  extends: DefaultTheme,
  enhanceApp({ router }) {
    if (import.meta.env.SSR) {
      return;
    }
    router.onAfterRouteChange = () => {
      void runMermaid();
    };
    void runMermaid();
  },
} satisfies Theme;
