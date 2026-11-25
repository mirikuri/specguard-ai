import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { parse, type Block, type Piece } from '../document'
import * as L from '../labels'
import type { Finding, Report } from '../types'

const GAP = 12

function useNarrow() {
  const [narrow, set] = useState(() => matchMedia('(max-width: 1000px)').matches)
  useEffect(() => {
    const m = matchMedia('(max-width: 1000px)'), on = () => set(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return narrow
}

const pieces = (b: Block): Piece[] => (b.kind === 'table' ? b.rows.flatMap((r) => r.cells.flat()) : b.pieces)

/** Документ с замечаниями на полях: каждое стоит напротив первой цитаты. */
export function Review({ r, list, current, pick }: { r: Report; list: Finding[]; current: string | null; pick: (id: string | null) => void }) {
  const narrow = useNarrow()
  const sheet = useRef<HTMLDivElement>(null)
  const margin = useRef<HTMLDivElement>(null)
  const pdf = /\.pdf$/i.test(r.document_name)
  const chars = useMemo(() => Array.from(r.document_text), [r.document_text])
  const blocks = useMemo(() => parse(r.document_text, pdf), [r, pdf])
  const spans = useMemo(() => list.flatMap((f) => f.evidence.map((e, k) => ({ f, k, start: e.start, end: e.end }))), [list])
  const ordered = useMemo(() => [...list].sort((a, b) => (a.evidence[0]?.start ?? 0) - (b.evidence[0]?.start ?? 0)), [list])

  const draw = (list: Piece[]): ReactNode => list.map((p) => {
    const near = spans.filter((s) => s.start < p.end && s.end > p.start)
    const cuts = [...new Set([p.start, p.end, ...near.flatMap((s) => [Math.max(s.start, p.start), Math.min(s.end, p.end)])])].sort((a, b) => a - b)
    const body = cuts.slice(0, -1).map((from, i) => {
      const to = cuts[i + 1], text = chars.slice(from, to).join('')
      const own = near.filter((s) => s.start <= from && s.end >= to).sort((a, b) => L.SEVERITIES.indexOf(a.f.severity) - L.SEVERITIES.indexOf(b.f.severity))
      if (!own.length) return <Fragment key={from}>{text}</Fragment>
      const on = own.some((s) => s.f.id === current)
      return <mark key={from} className={`${own[0].f.severity} ${on ? 'on' : ''}`} data-f={own.map((s) => `${s.f.id}:${s.k}`).join(' ')}
        onClick={() => {
          const at = own.findIndex((s) => s.f.id === current) // повторный щелчок переходит к следующему замечанию того же места
          pick(own[(at + 1) % own.length].f.id)
        }}>{text}</mark>
    })
    const key = p.start
    const inner = p.code ? <code>{body}</code> : body
    return p.bold ? <b key={key}>{inner}</b> : <Fragment key={key}>{inner}</Fragment>
  })

  // Замечание относится к блоку, где начинается его первая цитата
  const byBlock = useMemo(() => {
    const ends = blocks.map((b) => pieces(b).at(-1)?.end ?? 0)
    const map = new Map<number, Finding[]>()
    for (const f of ordered) {
      const i = Math.max(0, ends.findIndex((e) => e > (f.evidence[0]?.start ?? 0)))
      map.set(i, [...(map.get(i) ?? []), f])
    }
    return map
  }, [blocks, ordered])

  const layout = useCallback(() => {
    const box = margin.current, doc = sheet.current
    if (!box || !doc) return
    const base = box.getBoundingClientRect().top
    const notes = [...box.querySelectorAll<HTMLElement>('.note')].map((el) => {
      const mark = doc.querySelector(`mark[data-f~="${el.dataset.id}:0"]`)
      return { el, want: mark ? mark.getBoundingClientRect().top - base - 2 : 0, h: el.offsetHeight, top: 0 }
    })
    const at = notes.findIndex((n) => n.el.dataset.id === current)
    if (at >= 0) {
      notes[at].top = notes[at].want
      for (let i = at - 1; i >= 0; i--) notes[i].top = Math.min(notes[i].want, notes[i + 1].top - notes[i].h - GAP)
    }
    const shift = at > 0 ? Math.max(0, -notes[0].top) : 0
    for (let i = 0, floor = 0; i < notes.length; i++) {
      const n = notes[i]
      n.top = Math.max(at >= 0 && i <= at ? n.top : n.want, floor, shift && i <= at ? n.top + shift : 0)
      floor = n.top + n.h + GAP
      n.el.style.transform = `translateY(${Math.round(n.top)}px)`
    }
    const last = notes.at(-1)
    box.style.minHeight = last ? `${last.top + last.h}px` : ''
  }, [current])

  useLayoutEffect(() => {
    if (narrow) return
    layout()
    const ro = new ResizeObserver(layout)
    if (sheet.current) ro.observe(sheet.current)
    margin.current?.querySelectorAll('.note').forEach((n) => ro.observe(n))
    return () => ro.disconnect()
  }, [layout, narrow, list])

  useEffect(() => {
    if (!current) return
    const mark = sheet.current?.querySelector(`mark[data-f~="${current}:0"]`)
    const box = mark?.getBoundingClientRect()
    if (mark && box && (box.top < 60 || box.bottom > innerHeight - 80))
      mark.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [current])

  const step = (e: KeyboardEvent, f: Finding) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const next = ordered[ordered.indexOf(f) + (e.key === 'ArrowDown' ? 1 : -1)]
    if (!next) return
    e.preventDefault()
    pick(next.id)
    document.getElementById(`note-${next.id}`)?.focus({ preventScroll: true })
  }
  const go = (f: Finding, k: number) =>
    sheet.current?.querySelector(`mark[data-f~="${f.id}:${k}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })

  const name = (id: string | null) => {
    const x = r.requirements.find((q) => q.id === id)
    return x?.source_id ?? x?.id
  }
  const note = (f: Finding) => {
    const on = f.id === current
    const others = f.evidence.map((e, k) => ({ k, name: name(e.requirement_id) ?? e.section.split(' / ').at(-1) ?? '' })).slice(1)
    return (
      <aside key={f.id} className={`note ${f.severity} ${on ? 'on' : ''}`} data-id={f.id}>
        <button id={`note-${f.id}`} className="note-head" aria-expanded={on} onClick={() => pick(on ? null : f.id)} onKeyDown={(e) => step(e, f)}>
          <span className="note-meta">{f.id} {L.SEVERITY[f.severity].toLowerCase()}{f.status === 'needs_review' && ', требует решения'}</span>
          <span className="note-title">{f.title}</span>
        </button>
        {others.length > 0 && <p className="see">см. {others.map((o, i) => <Fragment key={o.k}>{i > 0 && ', '}<button className="link" onClick={() => { pick(f.id); go(f, o.k) }}>{o.name}</button></Fragment>)}</p>}
        {on && <FindingBody f={f} copy />}
      </aside>
    )
  }

  return (
    <div className="review">
      <div className={pdf ? 'sheet pdf' : 'sheet'} ref={sheet}>
        {blocks.map((b, i) => <Fragment key={i}>
          {b.kind === 'table'
            ? <div className="scroll"><table><tbody>{b.rows.map((row, n) => <tr key={n}>{row.cells.map((c, m) => row.head ? <th key={m}>{draw(c)}</th> : <td key={m}>{draw(c)}</td>)}</tr>)}</tbody></table></div>
            : b.kind === 'heading' ? <p role="heading" aria-level={Math.min(b.level + 1, 6)} className={`h h${b.level}`}>{draw(b.pieces)}</p>
            : b.kind === 'item' ? <p className="item" style={{ marginLeft: `${b.depth * 1.5}rem` }}><span>{b.marker}</span><span>{draw(b.pieces)}</span></p>
            : b.kind === 'code' ? <pre>{draw(b.pieces)}</pre>
            : <p>{draw(b.pieces)}</p>}
          {narrow && byBlock.get(i)?.map(note)}
        </Fragment>)}
      </div>
      {!narrow && <div className="margin" ref={margin}>{ordered.map(note)}</div>}
    </div>
  )
}

export function FindingBody({ f, copy }: { f: Finding; copy?: boolean }) {
  const [state, setState] = useState('')
  const fix = f.fix
  return (
    <dl className="finding">
      <dt>Причина</dt><dd>{f.explanation}</dd>
      <dt>Последствия</dt><dd>{f.impact}</dd>
      {fix ? <>
        <dt>Исправление</dt><dd className="fix">{fix.proposed_text || f.recommendation}</dd>
        {fix.acceptance_criteria && <><dt>Критерий приёмки</dt><dd>{fix.acceptance_criteria}</dd></>}
        {fix.clarification_required && <><dt>Вопрос аналитику</dt><dd>{fix.clarification_question}</dd></>}
      </> : <><dt>Рекомендация</dt><dd>{f.recommendation}</dd></>}
      {copy && <dd><button className="link" onClick={async () => {
        try { await navigator.clipboard.writeText(fix?.proposed_text || f.recommendation); setState('Скопировано') } catch { setState('Не удалось скопировать') }
        setTimeout(() => setState(''), 2000)
      }}>{state || 'Скопировать'}</button></dd>}
    </dl>
  )
}
