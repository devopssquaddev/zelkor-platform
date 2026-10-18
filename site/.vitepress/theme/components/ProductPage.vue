<script setup lang="ts">
import { computed } from 'vue'
import type { ProductSlug } from '../copy/types'
import { copy } from '../variant'
import Ctas from './Ctas.vue'

const props = defineProps<{ slug: ProductSlug }>()
const page = computed(() => copy.value.products[props.slug])
</script>

<template>
  <header class="page-hero wrap">
    <div class="eyebrow">{{ page.eyebrow }}</div>
    <h1>{{ page.h1 }}</h1>
    <p class="sub">{{ page.subtitle }}</p>
    <Ctas :primary="page.primaryCta" :secondary="page.secondaryCta" />
  </header>
  <div class="overview wrap">
    <h2>{{ page.overviewTitle }}</h2>
    <p>{{ page.overview }}</p>
  </div>
  <section class="block">
    <div class="wrap">
      <div class="grid-2">
        <article v-for="item in page.capabilities" :key="item.title" class="card">
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </article>
      </div>
      <h2 class="section-title" style="margin: 48px 0 16px; font-size: 1.6rem">{{ page.snippetTitle }}</h2>
      <pre class="code">{{ page.snippet }}</pre>
    </div>
  </section>
  <section class="final wrap">
    <h2 class="section-title">{{ page.bottomHeadline }}</h2>
    <Ctas :primary="page.bottomPrimary" :secondary="page.bottomSecondary" />
  </section>
</template>
