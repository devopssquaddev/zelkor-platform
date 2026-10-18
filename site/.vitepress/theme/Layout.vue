<script setup lang="ts">
import { Content, useData } from 'vitepress'
import { computed, onMounted } from 'vue'
import EditionsPage from './components/EditionsPage.vue'
import HomePage from './components/HomePage.vue'
import ProductPage from './components/ProductPage.vue'
import SiteFooter from './components/SiteFooter.vue'
import SiteNav from './components/SiteNav.vue'
import SolutionPage from './components/SolutionPage.vue'
import VariantSwitcher from './components/VariantSwitcher.vue'
import type { ProductSlug, SolutionSlug } from './copy/types'
import { initVariant, variantAttr, variantId } from './variant'

const { frontmatter, page } = useData()

const kind = computed(() => (frontmatter.value.page as string | undefined) ?? 'content')
const productSlug = computed(() => frontmatter.value.slug as ProductSlug)
const solutionSlug = computed(() => frontmatter.value.slug as SolutionSlug)

onMounted(() => initVariant())
</script>

<template>
  <div class="zk-site" :data-variant="variantAttr(variantId)">
    <VariantSwitcher />
    <SiteNav />
    <main class="zk-main">
      <HomePage v-if="kind === 'home'" />
      <ProductPage v-else-if="kind === 'product'" :slug="productSlug" />
      <SolutionPage v-else-if="kind === 'solution'" :slug="solutionSlug" />
      <EditionsPage v-else-if="kind === 'editions'" />
      <div v-else-if="page.isNotFound" class="hero wrap">
        <h1>Page not found</h1>
        <p class="sub">That route is not on the Zelkor site.</p>
        <a class="btn btn-primary" href="/">Home</a>
      </div>
      <Content v-else />
    </main>
    <SiteFooter />
  </div>
</template>
