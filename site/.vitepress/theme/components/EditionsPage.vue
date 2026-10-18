<script setup lang="ts">
import { resolveHref } from '../href'
import { copy } from '../variant'
import Ctas from './Ctas.vue'
</script>

<template>
  <header class="page-hero wrap">
    <div class="eyebrow">{{ copy.editions.eyebrow }}</div>
    <h1>{{ copy.editions.h1 }}</h1>
    <p class="sub">{{ copy.editions.subtitle }}</p>
    <Ctas :primary="copy.editions.primaryCta" :secondary="copy.editions.secondaryCta" />
  </header>
  <section class="block">
    <div class="wrap">
      <div class="editions">
        <article
          v-for="card in copy.editions.cards"
          :key="card.name"
          class="edition"
          :class="{ lead: card.featured }"
        >
          <div class="kicker">{{ card.kicker }}</div>
          <h3>{{ card.name }}</h3>
          <p>{{ card.tagline }}</p>
          <ul>
            <li v-for="item in card.highlights" :key="item">{{ item }}</li>
          </ul>
          <a class="btn btn-primary" style="margin-top: 16px" :href="resolveHref(card.cta.href)">{{ card.cta.label }}</a>
        </article>
      </div>
    </div>
  </section>
  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">Compare</div>
      <h2 class="section-title">Feature matrix</h2>
      <div class="table-wrap" style="margin-top: 28px">
        <table>
          <thead>
            <tr>
              <th>{{ copy.editions.matrixLabels?.capability ?? 'Capability' }}</th>
              <th>{{ copy.editions.matrixLabels?.ce ?? 'Community' }}</th>
              <th>{{ copy.editions.matrixLabels?.pro ?? 'Pro' }}</th>
              <th>{{ copy.editions.matrixLabels?.enterprise ?? 'Enterprise' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in copy.editions.matrix" :key="row.capability">
              <td><strong>{{ row.capability }}</strong></td>
              <td>{{ row.ce }}</td>
              <td>{{ row.pro }}</td>
              <td>{{ row.enterprise }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">FAQ</div>
      <h2 class="section-title">Questions</h2>
      <div class="faq" style="margin-top: 28px; max-width: 48rem; margin-left: auto; margin-right: auto">
        <details v-for="item in copy.editions.faqs" :key="item.q">
          <summary>{{ item.q }}</summary>
          <p>{{ item.a }}</p>
        </details>
      </div>
    </div>
  </section>
  <section v-if="copy.editions.finalHeadline" class="final wrap">
    <h2 class="section-title">{{ copy.editions.finalHeadline }}</h2>
    <p>{{ copy.editions.finalSub }}</p>
    <Ctas
      :primary="copy.editions.finalPrimary ?? copy.editions.primaryCta"
      :secondary="copy.editions.finalSecondary ?? copy.editions.secondaryCta"
    />
  </section>
</template>
