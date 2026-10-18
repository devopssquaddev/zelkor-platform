<script setup lang="ts">
import { ref } from 'vue'
import { docsUrl, githubUrl } from '../../links'
import { resolveHref } from '../href'
import { copy } from '../variant'

const open = ref(false)
</script>

<template>
  <div v-if="copy.announcement" class="announce">
    <div class="announce-inner">
      <span class="badge">{{ copy.announcement.badge }}</span>
      <span>{{ copy.announcement.text }}</span>
      <a :href="resolveHref(copy.announcement.href)">{{ copy.announcement.linkLabel }}</a>
    </div>
  </div>
  <nav class="nav">
    <div class="nav-inner">
      <a class="brand" href="/">
        <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <rect width="32" height="32" rx="6" fill="#0B0F19"/>
          <path d="M8 5h16a3 3 0 0 1 3 3v4" stroke="#F8FAFC" stroke-width="2"/>
          <path d="M27 18v6a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3" stroke="#F8FAFC" stroke-width="2"/>
          <path d="M27 12.2v1.4M27 18.8v-1.4" stroke="#3B82F6" stroke-width="2"/>
          <rect x="11" y="13" width="6" height="6" fill="#F8FAFC"/>
        </svg>
        <span>Zelkor</span>
        <span v-if="copy.brandSub" class="brand-sub">{{ copy.brandSub }}</span>
      </a>
      <button class="menu-toggle" type="button" :aria-expanded="open" @click="open = !open">Menu</button>
      <div class="menu" :class="{ open }">
        <div class="drop">
          <button type="button">Products</button>
          <div class="drop-panel">
            <a
              v-for="item in copy.productsNav"
              :key="item.slug"
              :href="`/products/${item.slug}`"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.blurb }}</span>
            </a>
          </div>
        </div>
        <div class="drop">
          <button type="button">Solutions</button>
          <div class="drop-panel solutions">
            <a
              v-for="item in copy.solutionsNav"
              :key="item.slug"
              :href="`/solutions/${item.slug}`"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.blurb }}</span>
            </a>
          </div>
        </div>
        <a href="/editions">Editions</a>
        <a :href="docsUrl">Docs</a>
        <a :href="githubUrl">GitHub</a>
      </div>
      <div class="nav-right">
        <a class="pill" :href="resolveHref(copy.navCta.href)">{{ copy.navCta.label }}</a>
      </div>
    </div>
  </nav>
</template>
