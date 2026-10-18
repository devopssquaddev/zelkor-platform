<script setup lang="ts">
import { resolveHref } from '../href'
import type { Cta } from '../copy/types'

defineProps<{ primary: Cta; secondary: Cta }>()
</script>

<template>
  <div class="ctas">
    <a class="btn btn-primary" :href="resolveHref(primary.href)">{{ primary.label }}</a>
    <a class="btn btn-secondary" :href="resolveHref(secondary.href)">{{ secondary.label }}</a>
  </div>
</template>
