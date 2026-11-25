import { useEffect, useMemo, useRef } from 'react'
import type { Finding, Severity } from '../types'

const RANK: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
export interface Span { start: number; end: number }

/** Исходный текст с подсветкой. Смещения считаются в символах Unicode, как в Python. */
export function SourceDocument({ text, findings, active, onPick }: { text: string; findings: Finding[]; active: Span[]; onPick: (f: Finding) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const pieces = useMemo(() => {
    const chars = Array.from(text)
    const cuts = new Set([0, chars.length])
    for (const f of findings) for (const e of f.evidence) { cuts.add(e.start); cuts.add(e.end) }
    for (const a of active) { cuts.add(a.start); cuts.add(a.end) }
    const points = [...cuts].sort((a, b) => a - b)
    return points.slice(0, -1).map((start, i) => {
      const end = points[i + 1]
      const own = findings
        .filter((f) => f.evidence.some((e) => e.start <= start && e.end >= end))
        .sort((a, b) => RANK.indexOf(a.severity) - RANK.indexOf(b.severity))
      return { start, text: chars.slice(start, end).join(''), own, on: active.some((a) => a.start <= start && a.end >= end) }
    })
  }, [text, findings, active])

  useEffect(() => {
    let stale = false
    const show = () => {
      const el = box.current, mark = el?.querySelector<HTMLElement>('[data-on]')
      if (!stale && el && mark) el.scrollTo({ top: el.scrollTop + mark.getBoundingClientRect().top - el.getBoundingClientRect().top - 80 })
    }
    show()
    document.fonts.ready.then(show) // загрузка шрифта меняет высоту строк
    return () => { stale = true }
  }, [active])

  return (
    <div className="source" ref={box} tabIndex={0} aria-label="Исходный документ">
      {pieces.map((p) => p.own.length || p.on ? (
        <mark key={p.start} data-on={p.on || undefined} className={`${p.own[0]?.severity ?? ''} ${p.on ? 'on' : ''}`}
          title={p.own.map((f) => `${f.id} ${f.title}`).join('\n')} onClick={() => p.own[0] && onPick(p.own[0])}>{p.text}</mark>
      ) : <span key={p.start}>{p.text}</span>)}
    </div>
  )
}
