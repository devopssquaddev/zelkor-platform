<script setup lang="ts">
import { computed } from 'vue'
import type { SolutionSlug } from '../copy/types'
import { resolveHref } from '../href'
import { copy } from '../variant'
import Ctas from './Ctas.vue'

const props = defineProps<{ slug: SolutionSlug }>()
const page = computed(() => copy.value.solutions[props.slug])
</script>

<template>
  <header class="page-hero wrap">
    <div class="eyebrow">{{ page.eyebrow }}</div>
    <h1>{{ page.h1 }}</h1>
    <p class="sub">{{ page.subtitle }}</p>
    <Ctas :primary="page.primaryCta" :secondary="page.secondaryCta" />
  </header>
  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">Risks</div>
      <h2 class="section-title">Where it fails without a runtime boundary</h2>
      <div class="grid-6" style="margin-top: 28px">
        <article v-for="item in page.risks" :key="item.title" class="card">
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </article>
      </div>
    </div>
  </section>
  <section class="block" id="mapping">
    <div class="wrap">
      <div class="eyebrow center-eye">Controls</div>
      <h2 class="section-title">{{ page.mappingTitle }}</h2>
      <div class="table-wrap" style="margin-top: 28px">
        <table>
          <thead>
            <tr>
              <th>{{ page.mappingLabels?.framework ?? 'Framework' }}</th>
              <th>{{ page.mappingLabels?.requirement ?? 'Requirement' }}</th>
              <th>{{ page.mappingLabels?.control ?? 'Zelkor control' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in page.mapping" :key="row.framework">
              <td><strong>{{ row.framework }}</strong></td>
              <td>{{ row.requirement }}</td>
              <td>{{ row.control }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">Topologies</div>
      <h2 class="section-title">{{ page.scenariosTitle }}</h2>
      <div class="grid-3" style="margin-top: 28px">
        <article v-for="item in page.scenarios" :key="item.title" class="card">
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </article>
      </div>
    </div>
  </section>
  <section class="final wrap">
    <h2 class="section-title">{{ page.bottomHeadline }}</h2>
    <div class="ctas">
      <a class="btn btn-primary" :href="resolveHref(page.bottomCta.href)">{{ page.bottomCta.label }}</a>
      <a
        v-if="page.bottomSecondary"
        class="btn btn-secondary"
        :href="resolveHref(page.bottomSecondary.href)"
      >{{ page.bottomSecondary.label }}</a>
    </div>
  </section>
</template>
