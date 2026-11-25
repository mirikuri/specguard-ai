import { Check as CheckIcon, Copy, Download, Printer } from 'lucide-react'
import { Fragment, useMemo, useState, type KeyboardEvent } from 'react'
import { api } from '../api'
import * as L from '../labels'
import type { Check, Finding, Report } from '../types'
import { Mosaic } from './Art'
import { DocumentView } from './DocumentView'

type Tab = 'findings' | 'requirements' | 'summary'
const MARK: Record<string, string> = { pass: '+', fail: '−', needs_review: '?', not_applicable: '·', not_evaluated: '' }

export function ReportView({ id, report: r }: { id: string; report: Report }) {
  const [tab, setTab] = useState<Tab>('findings')
  const [current, setCurrent] = useState<Finding | null>(r.findings[0] ?? null)
  const [quote, setQuote] = useState(0)
  const [severity, setSeverity] = useState('')
  const [status, setStatus] = useState('')
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const pick = (f: Finding) => { setCurrent(f); setQuote(0) }
  const open = (f: Finding) => { setSeverity(''); setStatus(''); setCategory(''); setQ(''); pick(f); setTab('findings') }
  const toggle = (s: string) => { setSeverity(severity === s ? '' : s); setStatus(''); setTab('findings') }
  const name = (rid: string | null) => { const x = r.requirements.find((y) => y.id === rid); return x?.source_id ?? x?.id }

  const list = useMemo(() => r.findings.filter((f) => (!severity || f.severity === severity) && (!status || f.status === status) && (!category || f.category === category)
    && (!q || `${f.id} ${f.title} ${f.requirement_ids.map(name).join(' ')} ${f.requirement_ids.join(' ')}`.toLowerCase().includes(q.trim().toLowerCase()))), [r, severity, status, category, q])
  const shown = current && list.includes(current) ? current : list[0] ?? null
  const step = (e: KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const next = list[list.indexOf(shown!) + (e.key === 'ArrowDown' ? 1 : -1)]
    if (!next) return
    e.preventDefault()
    pick(next)
    document.getElementById(`f-${next.id}`)?.focus()
  }

  return (
    <div className="page report">
      <section className="panel verdict">
        <Mosaic seed={id} cols={2} rows={2} className="verdict-art" />
        <div className={`gauge ${r.readiness.status}`}><b>{r.readiness.score ?? '–'}</b><span>{r.readiness.score == null ? 'нет оценки' : 'из 100'}</span></div>
        <div className="verdict-text"><h1>{r.document_name}</h1><b className={`state ${r.readiness.status}`}>{L.READINESS[r.readiness.status]}</b><p>{r.verdict.text}</p></div>
        <div className="counts">
          {L.SEVERITIES.slice(0, 4).map((s) => { const n = r.findings.filter((f) => f.severity === s).length; return <button key={s} className={`count ${s}`} aria-pressed={severity === s} disabled={!n} onClick={() => toggle(s)}><b>{n}</b>{L.SEVERITY[s]}</button> })}
          <button className="count" aria-pressed={status === 'needs_review'} disabled={!r.summary.needs_review_count} onClick={() => { setStatus(status ? '' : 'needs_review'); setSeverity(''); setTab('findings') }}><b>{r.summary.needs_review_count}</b>Требуют решения</button>
        </div>
      </section>
      <div className="toolbar panel">
        <div className="tabs" role="tablist">
          {([['findings', `Замечания (${r.findings.length})`], ['requirements', `Требования (${r.requirements.length})`], ['summary', 'Сводка и паспорт']] as const).map(([k, t]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t}</button>
          ))}
        </div>
        <div className="actions">{(['html', 'md', 'json'] as const).map((f) => <a key={f} className="btn" href={api.exportUrl(id, f)} download><Download aria-hidden />{{ html: 'HTML', md: 'Markdown', json: 'JSON' }[f]}</a>)}
          <button className="btn" onClick={() => window.print()}><Printer aria-hidden />Печать</button></div>
      </div>

      {tab === 'findings' && (r.findings.length === 0
        ? <section className="panel pad empty"><b>{r.status === 'completed' ? 'Замечаний нет' : 'Выполненные этапы не дали замечаний'}</b><span>{r.status === 'completed' ? 'Ни одна проблема не подтвердилась текстом документа.' : 'Проверка неполная. Повторите её, чтобы получить вывод.'}</span></section>
        : <div className="work">
          <section className="panel col list">
            <div className="filters">
              <input type="search" placeholder="Поиск по названию или номеру" aria-label="Поиск замечаний" value={q} onChange={(e) => setQ(e.target.value)} />
              <select aria-label="Категория" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">Все категории</option>{[...new Set(r.findings.map((f) => f.category))].map((c) => <option key={c} value={c}>{L.CATEGORY[c]}</option>)}</select>
              <select aria-label="Статус" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Любой статус</option><option value="confirmed">Подтверждено</option><option value="needs_review">Требует решения</option></select>
            </div>
            <ul onKeyDown={step}>{list.map((f) => (
              <li key={f.id}><button id={`f-${f.id}`} className={`row ${f.severity}`} aria-current={f === shown} onClick={() => pick(f)}>
                <span className="row-top"><span className={`tag ${f.severity}`}>{L.SEVERITY[f.severity]}</span>{f.status === 'needs_review' && <span className="tag review">Требует решения</span>}<span className="row-id">{f.id}</span></span>
                <b>{f.title}</b>
                <span className="dim">{L.CATEGORY[f.category]}{f.requirement_ids.length > 0 && `, ${f.requirement_ids.map(name).filter(Boolean).slice(0, 3).join(', ')}`}</span>
              </button></li>
            ))}{list.length === 0 && <li className="pad dim">Ничего не найдено. <button className="link" onClick={() => { setSeverity(''); setStatus(''); setCategory(''); setQ('') }}>Сбросить фильтры</button></li>}</ul>
          </section>
          <section className="panel col"><header className="panel-head"><h2>Документ</h2><span className="dim">цитаты выделены</span></header>
            <DocumentView r={r} list={list} current={shown} quote={quote} pick={pick} /></section>
          <section className="panel col detail" aria-live="polite">{shown && <Detail key={shown.id} f={shown} name={name} quote={quote} setQuote={setQuote} />}</section>
        </div>)}
      {tab === 'requirements' && <Requirements r={r} open={open} />}
      {tab === 'summary' && <Summary r={r} open={open} />}
      <section className="print-only"><h2>Замечания</h2>{r.findings.map((f) => <article key={f.id}><h3>{f.id}. {f.title}</h3><p>{L.SEVERITY[f.severity]}, {L.STATUS[f.status].toLowerCase()}</p>{f.evidence.map((e) => <blockquote key={e.start}>{e.quote}</blockquote>)}<Body f={f} /></article>)}</section>
    </div>
  )
}

function Body({ f }: { f: Finding }) {
  const x = f.fix
  return <>
    <h3>В чём проблема</h3><p>{f.explanation}</p>
    <h3>К чему приведёт</h3><p>{f.impact}</p>
    <h3>Что сделать</h3><p>{f.recommendation}</p>
    {x && <div className="fix"><h3>Вариант формулировки</h3><p>{x.proposed_text}</p>
      {x.acceptance_criteria && <><h3>Критерий приёмки</h3><p>{x.acceptance_criteria}</p></>}</div>}
    {x?.clarification_required && <div className="ask-box"><h3>Вопрос аналитику</h3><p>{x.clarification_question}</p></div>}
  </>
}

function Detail({ f, name, quote, setQuote }: { f: Finding; name: (id: string | null) => string | undefined; quote: number; setQuote: (n: number) => void }) {
  return <>
    <header className="detail-head"><span className="row-top"><span className={`tag ${f.severity}`}>{L.SEVERITY[f.severity]}</span><span className={`tag ${f.status === 'confirmed' ? 'ok' : 'review'}`}>{L.STATUS[f.status]}</span><span className="row-id">{f.id}</span></span><h2>{f.title}</h2></header>
    <div className="pad">
      <h3>{f.evidence.length > 1 ? `Цитаты (${f.evidence.length})` : 'Цитата'}</h3>
      {f.evidence.map((e, k) => (
        <button key={k} className="quote" aria-current={k === quote} title="Показать в документе" onClick={() => setQuote(k)}><span>{name(e.requirement_id) ?? e.section.split(' / ').at(-1)}{e.page ? `, стр. ${e.page}` : ''}</span>{L.clean(e.quote)}</button>
      ))}
      <Body f={f} />
      <CopyButton text={f.fix?.proposed_text || f.recommendation} />
      <p className="dim small">Источник: {L.SOURCE[f.source]}. Уверенность {Math.round(f.confidence * 100)}%. {f.validation_note}</p>
    </div>
  </>
}

function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState('')
  return <button className="btn" onClick={async () => {
    try { await navigator.clipboard.writeText(text); setState('Скопировано') } catch { setState('Не удалось скопировать') }
    setTimeout(() => setState(''), 2000)
  }}>{state === 'Скопировано' ? <CheckIcon aria-hidden /> : <Copy aria-hidden />}{state || 'Скопировать исправление'}</button>
}

function Checks({ items }: { items: Check[] }) {
  return <table className="checks"><tbody>{items.map((c) => (
    <tr key={c.criterion}><th scope="row">{L.CRITERION[c.criterion]}</th><td className={`st ${c.status}`}>{L.CHECK[c.status]}</td><td>{c.explanation}</td></tr>
  ))}</tbody></table>
}

function Requirements({ r, open }: { r: Report; open: (f: Finding) => void }) {
  const [q, setQ] = useState('')
  const [bad, setBad] = useState(false)
  const [on, setOn] = useState('')
  const cols = r.requirements[0]?.checks.map((c) => c.criterion) ?? []
  const list = r.requirements.filter((x) => `${x.id} ${x.source_id ?? ''} ${x.summary} ${x.text}`.toLowerCase().includes(q.trim().toLowerCase()) && (!bad || x.checks.some((c) => c.status === 'fail' || c.status === 'needs_review')))
  return (
    <section className="panel">
      <div className="filters line"><input type="search" placeholder="Поиск по номеру или тексту" aria-label="Поиск требований" value={q} onChange={(e) => setQ(e.target.value)} />
        <label><input type="checkbox" checked={bad} onChange={(e) => setBad(e.target.checked)} />Только с нарушениями и вопросами</label>
        <span className="legend"><i className="cell pass">+</i> выполнен <i className="cell fail">−</i> нарушен <i className="cell needs_review">?</i> уточнить <i className="cell not_evaluated" /> не оценён</span></div>
      <div className="scroll"><table className="matrix">
        <thead><tr><th className="no">Номер</th><th>Требование</th>{cols.map((c) => <th key={c} className="vert"><span>{L.CRITERION[c]}</span></th>)}</tr></thead>
        <tbody>{list.map((x) => {
          const own = r.findings.filter((f) => f.requirement_ids.includes(x.id))
          return <Fragment key={x.id}>
            <tr className={on === x.id ? 'on' : ''} onClick={() => setOn(on === x.id ? '' : x.id)}>
              <td><button className="link" aria-expanded={on === x.id} onClick={(e) => { e.stopPropagation(); setOn(on === x.id ? '' : x.id) }}>{x.source_id ?? x.id}</button></td><td>{x.summary}</td>
              {x.checks.map((c) => <td key={c.criterion} className="mid"><i className={`cell ${c.status}`} title={`${L.CRITERION[c.criterion]}: ${L.CHECK[c.status]}${c.explanation ? `. ${c.explanation}` : ''}`}>{MARK[c.status]}<span className="sr">{L.CHECK[c.status]}</span></i></td>)}
            </tr>
            {on === x.id && <tr className="open"><td colSpan={cols.length + 2}><div className="open-grid">
              <div><h3>Текст в документе</h3><p className="text">{L.clean(x.text)}</p><p className="dim">{x.id}{x.type_confidence ? `, ${L.lowerFirst(L.TYPE[x.requirement_type])}` : ''}, раздел «{x.section.split(' / ').at(-1)}»</p>
                <h3>Замечания</h3>{own.length ? own.map((f) => <p key={f.id}><button className="link" onClick={() => open(f)}>{f.id} {f.title}</button></p>) : <p className="dim">Нет</p>}</div>
              <Checks items={x.checks} /></div></td></tr>}
          </Fragment>
        })}</tbody></table></div>
      {list.length === 0 && <p className="pad dim">Требований по этому условию нет.</p>}
    </section>
  )
}

function Summary({ r, open }: { r: Report; open: (f: Finding) => void }) {
  const first = r.verdict.priorities.map((p) => r.findings.find((f) => p.startsWith(f.id + ' '))).filter((f) => f !== undefined)
  return (
    <div className="summary">
      <section className="panel"><header className="panel-head"><h2>Исправить в первую очередь</h2></header>
        {first.length ? <ol className="todo">{first.map((f) => <li key={f.id}><span className={`tag ${f.severity}`}>{L.SEVERITY[f.severity]}</span><div><button className="link" onClick={() => open(f)}>{f.title}</button><p>{f.recommendation}</p></div></li>)}</ol> : <p className="pad dim">Подтверждённых замечаний нет.</p>}</section>
      <section className="panel"><header className="panel-head"><h2>Из чего складывается оценка</h2></header>
        <div className="pad bars">{r.readiness.dimensions.map((d) => <div key={d.id}><span>{d.title}</span><i className="bar"><i style={{ width: `${d.score ?? 0}%` }} /></i><b>{d.score ?? '–'}</b></div>)}
          <p className="dim small">Учтено {r.readiness.coverage}% критериев.</p></div></section>
      <section className="panel"><header className="panel-head"><h2>Набор требований в целом</h2></header><div className="pad"><Checks items={r.set_checks} /></div></section>
      <section className="panel"><header className="panel-head"><h2>Паспорт проверки</h2></header><div className="pad"><table className="checks"><tbody>
        <tr><th scope="row">Документ</th><td>{r.document_name}</td></tr><tr><th scope="row">Дата</th><td>{new Date(r.analyzed_at).toLocaleString('ru-RU')}</td></tr>
        <tr><th scope="row">Длительность</th><td>{Math.round(r.duration_seconds)} с</td></tr><tr><th scope="row">Модели</th><td>{r.model_name}</td></tr><tr><th scope="row">Версия агента</th><td>{r.agent_version}</td></tr>
      </tbody></table><h3>Этапы</h3><table className="checks"><tbody>{r.stages.map((s) => <tr key={s.id}><th scope="row">{s.title}</th><td className={`st ${s.status === 'failed' ? 'fail' : s.status === 'partial' ? 'needs_review' : ''}`}>{L.STAGE[s.status]}</td><td>{s.message}</td></tr>)}</tbody></table></div></section>
      {r.rejected_findings.length > 0 && <section className="panel span"><header className="panel-head"><h2>Отброшено при перепроверке</h2><span className="dim">{r.rejected_findings.length}</span></header><div className="pad"><table className="checks"><tbody>{r.rejected_findings.map((f) => <tr key={f.id}><th scope="row">{f.title}</th><td>{f.validation_note}</td></tr>)}</tbody></table></div></section>}
    </div>
  )
}
