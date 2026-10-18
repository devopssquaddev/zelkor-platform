export type ProductSlug =
  | 'sandbox'
  | 'gateway'
  | 'mcp'
  | 'tenancy'
  | 'observability'
  | 'network'

export type SolutionSlug =
  | 'financial-services'
  | 'healthcare'
  | 'b2b-saas'
  | 'platform-engineering'

export type Cta = { label: string; href: string }

export type NavItem = { slug: string; title: string; blurb: string }

export type Tab = {
  id: string
  label: string
  headline: string
  copy: string
  points?: string[]
  code: string
  lang: 'yaml' | 'json' | 'bash' | 'sql'
}

export type Proof = {
  title: string
  scenario: string
  control: string
  result: string
}

export type Persona = {
  title: string
  role: string
  body: string
  points: string[]
}

export type ProductCopy = {
  slug: ProductSlug
  eyebrow: string
  h1: string
  subtitle: string
  primaryCta: Cta
  secondaryCta: Cta
  overviewTitle: string
  overview: string
  capabilities: { title: string; text: string }[]
  snippetTitle: string
  snippet: string
  snippetLang: 'yaml' | 'json' | 'sql' | 'bash'
  bottomHeadline: string
  bottomPrimary: Cta
  bottomSecondary: Cta
}

export type SolutionCopy = {
  slug: SolutionSlug
  eyebrow: string
  h1: string
  subtitle: string
  primaryCta: Cta
  secondaryCta: Cta
  risks: { title: string; text: string }[]
  mappingTitle: string
  mapping: { framework: string; requirement: string; control: string }[]
  mappingLabels?: { framework: string; requirement: string; control: string }
  scenariosTitle: string
  scenarios: { title: string; text: string }[]
  bottomHeadline: string
  bottomCta: Cta
  bottomSecondary?: Cta
}

export type EditionCard = {
  name: string
  kicker: string
  tagline: string
  highlights: string[]
  cta: Cta
  featured?: boolean
}

export type VariantCopy = {
  id: 1 | 2 | 3 | 4 | 5 | 6 | 7
  name: string
  short: string
  announcement: { badge: string; text: string; linkLabel: string; href: string }
  brandSub?: string
  navCta: Cta
  productsNav: NavItem[]
  solutionsNav: NavItem[]
  home: {
    eyebrow: string
    h1: string
    subtitle: string
    primaryCta: Cta
    secondaryCta: Cta
    githubCta?: Cta
    install: string
    marqueeLabel: string
    marquee: string[]
    bridgeKicker?: string
    bridgeHeading?: string
    bridge: string
    tabsHeadline: string
    tabs: Tab[]
    stepsHeadline: string
    stepsSub?: string
    steps: { title: string; subtitle?: string; body: string }[]
    proofsHeadline: string
    proofsSub?: string
    proofs: Proof[]
    personasHeadline: string
    personas: Persona[]
    finalHeadline: string
    finalSub: string
    finalPrimary: Cta
    finalSecondary: Cta
  }
  products: Record<ProductSlug, ProductCopy>
  solutions: Record<SolutionSlug, SolutionCopy>
  editions: {
    eyebrow: string
    h1: string
    subtitle: string
    primaryCta: Cta
    secondaryCta: Cta
    cards: EditionCard[]
    matrixLabels?: { capability: string; ce: string; pro: string; enterprise: string }
    matrix: { capability: string; ce: string; pro: string; enterprise: string }[]
    faqs: { q: string; a: string }[]
    finalHeadline?: string
    finalSub?: string
    finalPrimary?: Cta
    finalSecondary?: Cta
  }
}

export const PRODUCT_SLUGS: ProductSlug[] = [
  'sandbox',
  'gateway',
  'mcp',
  'tenancy',
  'observability',
  'network',
]

export const SOLUTION_SLUGS: SolutionSlug[] = [
  'financial-services',
  'healthcare',
  'b2b-saas',
  'platform-engineering',
]
