<script setup lang="ts">
import { ref } from 'vue'
import { resolveHref } from '../href'
import { copy } from '../variant'
import Ctas from './Ctas.vue'

const tab = ref(0)
const persona = ref(0)
</script>

<template>
  <header class="hero wrap" id="top">
    <div class="eyebrow">{{ copy.home.eyebrow }}</div>
    <h1>{{ copy.home.h1 }}</h1>
    <p class="sub">{{ copy.home.subtitle }}</p>
    <Ctas :primary="copy.home.primaryCta" :secondary="copy.home.secondaryCta" />
    <p v-if="copy.home.githubCta" class="hero-github">
      <a :href="resolveHref(copy.home.githubCta.href)">{{ copy.home.githubCta.label }}</a>
    </p>
    <pre class="install">{{ copy.home.install }}</pre>
  </header>

  <div class="marquee" :aria-label="copy.home.marqueeLabel">
    <div class="marquee-label">{{ copy.home.marqueeLabel }}</div>
    <div class="track">
      <span v-for="(item, i) in [...copy.home.marquee, ...copy.home.marquee]" :key="i" class="chip">
        <i></i>{{ item }}
      </span>
    </div>
  </div>

  <div class="bridge wrap">
    <div v-if="copy.home.bridgeKicker" class="kicker">{{ copy.home.bridgeKicker }}</div>
    <h2 v-if="copy.home.bridgeHeading">{{ copy.home.bridgeHeading }}</h2>
    <p>{{ copy.home.bridge }}</p>
  </div>

  <div class="panel wrap">
    <div class="eyebrow center-eye">Walkthrough</div>
    <h2 class="section-title" style="margin-bottom: 24px">{{ copy.home.tabsHeadline }}</h2>
    <div class="tabs" role="tablist">
      <button
        v-for="(item, i) in copy.home.tabs"
        :key="item.id"
        type="button"
        role="tab"
        :aria-selected="tab === i"
        @click="tab = i"
      >{{ item.label }}</button>
    </div>
    <div class="split">
      <div>
        <h3>{{ copy.home.tabs[tab].headline }}</h3>
        <p>{{ copy.home.tabs[tab].copy }}</p>
        <ul v-if="copy.home.tabs[tab].points?.length" class="tab-points">
          <li v-for="point in copy.home.tabs[tab].points" :key="point">{{ point }}</li>
        </ul>
      </div>
      <pre class="code">{{ copy.home.tabs[tab].code }}</pre>
    </div>
  </div>

  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">How it ships</div>
      <h2 class="section-title">{{ copy.home.stepsHeadline }}</h2>
      <p v-if="copy.home.stepsSub" class="section-sub">{{ copy.home.stepsSub }}</p>
      <div class="grid-3" style="margin-top: 32px">
        <article v-for="(step, i) in copy.home.steps" :key="step.title" class="card">
          <div class="num">{{ i + 1 }}</div>
          <h3>{{ step.title }}</h3>
          <p>{{ step.body }}</p>
        </article>
      </div>
    </div>
  </section>

  <section class="block" id="proofs">
    <div class="wrap">
      <div class="eyebrow center-eye">Proofs</div>
      <h2 class="section-title">{{ copy.home.proofsHeadline }}</h2>
      <p v-if="copy.home.proofsSub" class="section-sub">{{ copy.home.proofsSub }}</p>
      <div class="grid-6">
        <article v-for="item in copy.home.proofs" :key="item.title" class="card proof">
          <h3>{{ item.title }}</h3>
          <p><strong>Scenario.</strong> {{ item.scenario }}</p>
          <p style="margin-top: 8px"><strong>Control.</strong> {{ item.control }}</p>
          <p class="result">{{ item.result }}</p>
        </article>
      </div>
    </div>
  </section>

  <section class="block">
    <div class="wrap">
      <div class="eyebrow center-eye">Who it is for</div>
      <h2 class="section-title">{{ copy.home.personasHeadline }}</h2>
      <div class="personas" role="tablist" style="margin-top: 28px">
        <button
          v-for="(item, i) in copy.home.personas"
          :key="item.title"
          type="button"
          role="tab"
          :aria-selected="persona === i"
          @click="persona = i"
        >
          <b>{{ item.title }}</b>
          <span>{{ item.role }}</span>
        </button>
      </div>
      <div class="persona">
        <h3>{{ copy.home.personas[persona].title }}</h3>
        <p>{{ copy.home.personas[persona].body }}</p>
        <ul>
          <li v-for="point in copy.home.personas[persona].points" :key="point">{{ point }}</li>
        </ul>
      </div>
    </div>
  </section>

  <section class="final wrap" id="review">
    <h2 class="section-title">{{ copy.home.finalHeadline }}</h2>
    <p>{{ copy.home.finalSub }}</p>
    <Ctas :primary="copy.home.finalPrimary" :secondary="copy.home.finalSecondary" />
  </section>
</template>
