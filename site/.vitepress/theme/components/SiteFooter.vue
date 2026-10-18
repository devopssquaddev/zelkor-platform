<script setup lang="ts">
import { docsUrl, githubUrl } from '../../links'
import { resolveHref } from '../href'
import { copy } from '../variant'
</script>

<template>
  <footer class="site-foot">
    <div class="wrap cols">
      <div>
        <h2>Products</h2>
        <a
          v-for="item in copy.productsNav"
          :key="item.slug"
          :href="`/products/${item.slug}`"
        >{{ item.title }}</a>
      </div>
      <div>
        <h2>Solutions</h2>
        <a
          v-for="item in copy.solutionsNav"
          :key="item.slug"
          :href="`/solutions/${item.slug}`"
        >{{ item.title }}</a>
        <a href="/editions">Editions</a>
      </div>
      <div>
        <h2>Start</h2>
        <a :href="docsUrl">Docs</a>
        <a :href="githubUrl">GitHub</a>
        <a :href="resolveHref(copy.navCta.href)">{{ copy.navCta.label }}</a>
      </div>
    </div>
    <p class="legal">Zelkor Community Edition is Apache 2.0. {{ copy.name }} preview.</p>
  </footer>
</template>
