<script setup lang="ts">
import { VARIANT_META, setVariant, variantId } from '../variant'
</script>

<template>
  <div class="switcher-bar">
    <div class="switcher-inner">
      <span class="switcher-label">6-variant preview</span>
      <div class="switcher-pills" role="group" aria-label="Copy and theme variant">
        <button
          v-for="item in VARIANT_META"
          :key="item.id"
          type="button"
          :aria-pressed="variantId === item.id"
          :title="item.name"
          @click="setVariant(item.id)"
        >
          {{ item.short }}
        </button>
      </div>
    </div>
  </div>
</template>
