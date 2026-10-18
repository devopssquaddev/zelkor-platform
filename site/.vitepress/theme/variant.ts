import { computed, ref, watch } from 'vue'
import { variants } from './copy'
import type { VariantCopy } from './copy/types'

export const VARIANT_META = [
  { id: 1 as const, name: 'Cobalt Precision', short: 'Cobalt' },
  { id: 2 as const, name: 'Obsidian Perimeter', short: 'Obsidian' },
  { id: 3 as const, name: 'Swiss Editorial', short: 'Swiss' },
  { id: 4 as const, name: 'Signal Crimson-Slate', short: 'Signal' },
  { id: 5 as const, name: 'Emerald Control Plane', short: 'Emerald' },
  { id: 6 as const, name: 'Emerald Defense', short: '6 · Emerald' },
]

export type VariantId = (typeof VARIANT_META)[number]['id']

const KEY = 'zelkor-site-variant-v6'

export const variantId = ref<VariantId>(6)

export const copy = computed<VariantCopy>(() => variants[variantId.value])

export function variantAttr(id: VariantId): string {
  return id === 6 ? 'v6' : String(id)
}

export function setVariant(id: VariantId) {
  variantId.value = id
}

export function initVariant() {
  if (typeof window === 'undefined') return
  const raw = window.localStorage.getItem(KEY)
  if (raw === 'v6' || raw === '6') {
    variantId.value = 6
    return
  }
  const n = Number(raw)
  if (n >= 1 && n <= 6) variantId.value = n as VariantId
}

watch(
  variantId,
  (id) => {
    if (typeof document === 'undefined') return
    document.documentElement.dataset.variant = variantAttr(id)
    try {
      window.localStorage.setItem(KEY, variantAttr(id))
    } catch {
      /* ignore quota / private mode */
    }
  },
  { immediate: true },
)
