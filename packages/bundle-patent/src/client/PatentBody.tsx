/**
 * The dashboard's asynchronous body: performs the workspace listings for the
 * open session's project directory, derives the overview, and offers a manual
 * refresh. All state is component-local; the session id arrives as a standard
 * slot prop (the tab slot is session-scoped).
 * @module
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { buildProjectView, type ProjectView } from './project-model.ts'
import type { PatentProjectInjected } from './patent-face.ts'
import { ProjectOverview } from './ProjectOverview.tsx'
import css from './PatentBody.module.css'

type PatentBodyProps =
  & PropsRuntime<'sidebar.right.pane.tab'>
  & PropsLocale<'patent'>
  & PatentProjectInjected

/**
 * Render the project overview for the open session's workspace.
 * @param props - tab slot props (sessionId included), the injected face, and copy.
 * @returns the dashboard body.
 */
export function PatentBody({ listDirectory, readProjectFile, t }: PatentBodyProps): ReactNode {
  const [view, setView] = useState<ProjectView | null>(null)
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const root = await listDirectory('.', new AbortController().signal)
      if (root === null) {
        setFailed(true)
        setView(null)
        return
      }
      const names = new Set(root.entries.map(entry => entry.name))
      const has = (name: string): boolean => names.has(name)
      const [chapters, review, figures, application, experiments, exports, yml, drawings] = await Promise.all([
        has('chapters') ? listDirectory('chapters', new AbortController().signal) : Promise.resolve(null),
        has('review') ? listDirectory('review', new AbortController().signal) : Promise.resolve(null),
        has('figures') ? listDirectory('figures', new AbortController().signal) : Promise.resolve(null),
        has('application') ? listDirectory('application', new AbortController().signal) : Promise.resolve(null),
        has('experiments') ? listDirectory('experiments', new AbortController().signal) : Promise.resolve(null),
        has('exports') ? listDirectory('exports', new AbortController().signal) : Promise.resolve(null),
        has('patent.yml') ? readProjectFile('patent.yml', new AbortController().signal) : Promise.resolve(null),
        has('chapters') ? readProjectFile('chapters/08-drawings.md', new AbortController().signal) : Promise.resolve(null),
      ])
      // Second phase — the texts the coarse loop summary consumes. Each read
      // fails soft (null): the panel degrades to presence-only facts instead
      // of blocking on one missing file.
      const reportNames = (review?.entries ?? [])
        .filter(entry => entry.type === 'file' && entry.name.endsWith('.review.md'))
        .map(entry => entry.name)
        .slice(0, 4)
      const experimentDirs = (experiments?.entries ?? [])
        .filter(entry => entry.type === 'directory')
        .map(entry => entry.name)
        .slice(0, 4)
      const [briefText, effectText, priorArtText, experimentsReadme, ...rest] = await Promise.all([
        has('brief.md') ? readProjectFile('brief.md', new AbortController().signal) : Promise.resolve(null),
        has('chapters') ? readProjectFile('chapters/06-effect.md', new AbortController().signal) : Promise.resolve(null),
        has('reference') ? readProjectFile('reference/prior-art.md', new AbortController().signal) : Promise.resolve(null),
        has('experiments') ? readProjectFile('experiments/README.md', new AbortController().signal) : Promise.resolve(null),
        ...reportNames.map(name => readProjectFile(`review/${name}`, new AbortController().signal)),
        ...experimentDirs.map(name => readProjectFile(`experiments/${name}/results/run-log.md`, new AbortController().signal)),
      ])
      const reportTexts = reportNames.map((name, index) => ({ name, text: rest[index] ?? null }))
      const experimentRunLogs = rest.slice(reportNames.length).map((text) => {
        const latest = text?.replace(/```[\s\S]*?```/g, '').split(/^## /m).at(-1)?.split('- 输出尾部：')[0]
        return latest !== undefined && /^- 退出码：0\s*$/m.test(latest)
      })
      setView(buildProjectView(root, chapters, review, figures, application, yml, drawings, {
        briefText,
        effectText,
        priorArtText,
        experimentsReadmeText: experimentsReadme,
        experimentRunLogs,
        exportsListing: exports,
        reportTexts,
      }))
      setFailed(false)
    } finally {
      setLoading(false)
    }
  }, [listDirectory, readProjectFile])

  useEffect(() => {
    void load()
  }, [load])

  if (failed) {
    return (
      <div className={css.body}>
        <span className={css.empty}>{t('panel.unreadable')}</span>
      </div>
    )
  }
  if (view === null) {
    return (
      <div className={css.body}>
        <span className={css.empty}>{t('panel.loading')}</span>
      </div>
    )
  }
  if (!view.isProject) {
    return (
      <div className={css.body}>
        <span className={css.empty}>{t('panel.notProject')}</span>
      </div>
    )
  }
  return (
    <div className={css.body}>
      <div className={css.head}>
        <span className={css.projectName}>{view.projectName ?? t('panel.title')}</span>
        <button type="button" className={css.refresh} disabled={loading} onClick={() => { void load() }}>
          {loading ? t('panel.loading') : t('panel.refresh')}
        </button>
      </div>
      <ProjectOverview view={view} t={t} />
    </div>
  )
}
