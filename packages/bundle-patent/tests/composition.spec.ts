import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { parse as parseYaml } from 'yaml'
import { describe, expect, it } from 'vitest'

interface PatchRow {
  id?: string
  name?: string
  config?: Record<string, unknown>
  disabled?: boolean
  insert?: PatchRow[]
}

const patchPath = fileURLToPath(new URL('../cordis.patch.yml', import.meta.url))

async function loadPatch(): Promise<PatchRow[]> {
  return parseYaml(await readFile(patchPath, 'utf8')) as PatchRow[]
}

describe('the patent bundle patch', () => {
  it('leaves the persona to the profile layer — no system-prompt row', async () => {
    const rows = await loadPatch()
    expect(rows.find(row => row.id === 'system-prompt')).toBeUndefined()
  })

  it('re-enables the host-plane workflow engine the web composition disables', async () => {
    const rows = await loadPatch()
    const engine = rows.find(row => row.id === 'workflow-ptc')
    expect(engine?.disabled).toBe(false)
  })

  it('inserts the coverage tool, the asset carrier, the review command, and the gated MCP rows', async () => {
    const rows = await loadPatch()
    const inserted = rows.find(row => Array.isArray(row.insert))?.insert ?? []
    expect(inserted).toEqual([
      { id: 'tool-patent', name: '@mtl-academic/dsh-tool-patent' },
      { id: 'patent-assets', name: '@mtl-academic/dsh-patent' },
      { id: 'command-patent-review', name: '@mtl-academic/dsh-command-patent-review' },
      expect.objectContaining({ id: 'mcp-patent-services', name: '@deepseek-ai/dsh-mcp-client' }),
    ])
  })
})
