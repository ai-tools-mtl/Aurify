/**
 * Package-owned invariant companion for `@mtl-academic/dsh-command-patent-review`.
 * @module @mtl-academic/dsh-command-patent-review/invariant
 */

import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@mtl-academic/dsh-command-patent-review'

/** Cordis companion plugin name. */
export const name = 'command-patent-review-invariant'
/** Service required before the companion can register. */
export const inject = ['invariants']

// No runtime invariant: the package registers one human command whose handler
// owns no durable event stream (command/run and command/done are the registry's
// events; the report is an ordinary file) and no mutable relationship.
const install: InvariantInstaller = () => {}

/**
 * Register this package's invariant companion.
 * @param ctx - Cordis context carrying the invariant service.
 * @returns the installed registration's disposer after setup succeeds.
 */
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
