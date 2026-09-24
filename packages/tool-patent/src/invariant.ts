/**
 * Package-owned invariant companion for `@mtl-academic/dsh-tool-patent`.
 * @module @mtl-academic/dsh-tool-patent/invariant
 */

import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@mtl-academic/dsh-tool-patent'

/** Cordis companion plugin name. */
export const name = 'tool-patent-invariant'
/** Service required before the companion can register. */
export const inject = ['invariants']

// No runtime invariant: the package registers one pure model-facing scoring
// tool; it appends no durable event of its own (calls and results ride the
// loop's tool/call and tool/result events) and owns no mutable relationship.
const install: InvariantInstaller = () => {}

/**
 * Register this package's invariant companion.
 * @param ctx - Cordis context carrying the invariant service.
 * @returns the installed registration's disposer after setup succeeds.
 */
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
