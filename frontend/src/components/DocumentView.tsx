import { Fragment, useEffect, useMemo, useRef, type ReactNode } from 'react'
import { parse, type Piece } from '../document'
import * as L from '../labels'
import type { Finding, Report } from '../types'

/** Исходный документ с подсветкой цитат. */
export function DocumentView({ r, list, current, quote, pick }: { r: Report; list: Finding[]; current: Finding | null; quote: number; pick: (f: Finding) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const pdf = /\.pdf$/i.test(r.document_name)
  const chars = useMemo(() => Array.from(r.document_text), [r.document_text])
  const blocks = useMemo(() => parse(r.document_text, pdf), [r, pdf])
  const spans = useMemo(() => list.flatMap((f) => f.evidence.map((e, k) => ({ f, k, start: e.start, end: e.end }))), [list])

  const draw = (ps: Piece[]): ReactNode => ps.map((p) => {
    const near = spans.filter((s) => s.start < p.end && s.end > p.start)
    const cuts = [...new Set([p.start, p.end, ...near.flatMap((s) => [Math.max(s.start, p.start), Math.min(s.end, p.end)])])].sort((a, b) => a - b)
    const body = cuts.slice(0, -1).map((from, i) => {
      const to = cuts[i + 1], text = chars.slice(from, to).join('')
      const own = near.filter((s) => s.start <= from && s.end >= to).sort((a, b) => L.SEVERITIES.indexOf(a.f.severity) - L.SEVERITIES.indexOf(b.f.severity))
      if (!own.length) return <Fragment key={from}>{text}</Fragment>
      const at = own.findIndex((s) => s.f === current) // повторный щелчок переходит к следующему замечанию того же места
      return <mark key={from} className={`${own[0].f.severity} ${own.some((s) => s.f === current && s.k === quote) ? 'on' : at >= 0 ? 'same' : ''}`} data-f={own.map((s) => `${s.f.id}:${s.k}`).join(' ')}
        title={own.map((s) => s.f.title).join('\n')} onClick={() => pick(own[(at + 1) % own.length].f)}>{text}</mark>
    })
    const inner = p.code ? <code>{body}</code> : body
    return p.bold ? <b key={p.start}>{inner}</b> : <Fragment key={p.start}>{inner}</Fragment>
  })

  useEffect(() => {
    const el = box.current
    const mark = current && el?.querySelector(`mark[data-f~="${current.id}:${quote}"]`)
    if (!el || !mark) return
    const scrolls = el.scrollHeight > el.clientHeight + 1
    if (scrolls) el.scrollTo({ top: el.scrollTop + mark.getBoundingClientRect().top - el.getBoundingClientRect().top - el.clientHeight / 3 })
  }, [current, quote])

  return (
    <div className={pdf ? 'doc pdf' : 'doc'} ref={box} tabIndex={0} aria-label="Исходный документ">
      {blocks.map((b, i) => b.kind === 'table'
        ? <div key={i} className="scroll"><table><tbody>{b.rows.map((row, n) => <tr key={n}>{row.cells.map((c, m) => row.head ? <th key={m}>{draw(c)}</th> : <td key={m}>{draw(c)}</td>)}</tr>)}</tbody></table></div>
        : b.kind === 'heading' ? <p key={i} role="heading" aria-level={Math.min(b.level + 2, 6)} className={`h h${b.level}`}>{draw(b.pieces)}</p>
        : b.kind === 'item' ? <p key={i} className="item" style={{ marginLeft: `${b.depth * 1.25}rem` }}><span>{b.marker}</span><span>{draw(b.pieces)}</span></p>
        : b.kind === 'code' ? <pre key={i}>{draw(b.pieces)}</pre> : <p key={i}>{draw(b.pieces)}</p>)}
    </div>
  )
}
