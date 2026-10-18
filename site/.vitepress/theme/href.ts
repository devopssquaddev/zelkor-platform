import { contactEmail, docsUrl, formUrl, githubUrl } from '../links'

export function resolveHref(href: string): string {
  if (!href || href === '#docs' || href.startsWith('/docs')) return docsUrl
  if (
    href === '#review' ||
    href.startsWith('/contact') ||
    href.includes('architecture-review')
  ) {
    if (formUrl) return formUrl
    if (contactEmail) return `mailto:${contactEmail}`
    return '#review'
  }
  if (href.includes('github.com') || href === '#github') return githubUrl
  return href
}
