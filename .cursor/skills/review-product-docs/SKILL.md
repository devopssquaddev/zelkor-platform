---
name: review-product-docs
description: >-
  Reviews Zelkor public docs as target reader personas (novice app developer
  new to agent platforms, AI agents developer, platform/SRE, staff architect,
  coding agent, DevRel / engineering-as-marketing, and Sales / AE) and judges
  whether they can complete the page’s job. Use after writing or editing README,
  docs/, architecture, reference, KB, or when the user asks to review
  documentation for clarity, audience fit, marketing, or sales usability.
---

# Review product docs

Follow `.cursor/rules/product-docs.mdc`. Multi-root spec: `internal/requirements/dev/product_documentation.md` § Persona review.

Do not commit the review into `docs/`.

| Pages | Must pass |
| :--- | :--- |
| Root README, `docs/README.md`, `quickstart`, architecture, example READMEs | **Novice** + **Agent developer** + **DevRel** + **Sales** (outcome “You get…”, CE / Pro / Enterprise ladder, honest POC, no pitch) |
| `agent-deploy`, CLI, MCP extra backends, example READMEs | **Agent developer** |
| `production`, `helm-install`, topologies, `architecture` | **Platform** + **Architect** + **Sales** |
| `agent-install`, `agent-deploy` | **Agent** |

**Core advantage (shared):** Every required persona must state it in their own words from the page (or one linked page for a procedure): bring the agent you wrote; it is "sandboxed" — it can't break out, reach unauthorized data/networks, its prompts are verified, budget controlled, and it is under observation. Editions layer on that sandbox; they are not a substitute. Fail if only components/steps/edition names appear and the advantage is unsaid. Dry reference/KB: no pitch; fail only on contradiction. If a required persona cannot state the core advantage, the page fails even when other checks passed.

Read as that person. Fail if they cannot finish the page’s job, a load-bearing term is unexplained, or they cannot state the core advantage. Fix; re-run that persona only; then the next.

**Agent developer:** Keep the agent already written — no rewrite to add sandbox controls; land graph / call / MCP / trace without becoming an SRE; demo is not how they learn the platform.

**DevRel** (HN / r/devops reader): On README, docs index, and tutorials, fail if the first proof is a component list (Envoy, Aegra, gVisor, Langfuse) and they cannot say “I declare a model, a tool, and an agent,” or that those same objects run from laptop to production. Also fail if they cannot say that the agent is "sandboxed". Do not require the word “abstraction.” On architecture, fail if components appear with no boundary (what you set, what the platform generates), or if the hop is hidden. Also fail fluff, a TTFV claim without a pasteable path, a sales wall in front of Community Edition, and a hairball diagram.

**Sales** (AE with a prospect; “What does my customer get?”): “You get…” must be the core advantage in prospect words. Fail component-led opening; edition-split-alone as success (ladder required, not enough by itself); missing short ladder clause (CE = self-hosted runtime; Pro = SSO + team controls + HA/GitOps; Ent = isolation + compliance on Pro — hardware sandbox, mTLS, retained audit, BAA); prices/SKUs; buy-wall before CE runs; HIPAA claimed for CE. Do not fail for absent Kyverno/TOLAP/SCIM-style names.

Report in chat: `persona | pass/fail | blocker`.
