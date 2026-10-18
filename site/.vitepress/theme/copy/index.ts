import type { VariantCopy } from './types'
import { v1 } from './v1'
import { v2 } from './v2'
import { v3 } from './v3'
import { v4 } from './v4'
import { v5 } from './v5'
import { v6 } from './v6'
import { v7 } from './v7'

export const variants: Record<1 | 2 | 3 | 4 | 5 | 6 | 7, VariantCopy> = {
  1: v1,
  2: v2,
  3: v3,
  4: v4,
  5: v5,
  6: v6,
  7: v7,
}
