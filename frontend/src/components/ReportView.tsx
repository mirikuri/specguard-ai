import { useState } from 'react'
import { api } from '../api'
import * as L from '../labels'
import type { Check, Finding, Report } from '../types'
import { FindingBody, Review } from './Review'

export function ReportView({ id, report: r }: { id: string; report: Report }) {
  const [tab, setTab] = useState<'findings' | 'requirements' | 'run'>('findings')
  const [current, setCurrent] = useState<string | null>(null)
  const [severity, setSeverity] = useState('')
  const open = (f: Finding) => { setSeverity(''); setCurrent(f.id); setTab('findings') }
  const list = r.findings.filter((f) => !severity || (severity === 'needs_review' ? f.status === severity : f.severity === severity))
  const ordered = [...list].sort((a, b) => (a.evidence[0]?.start ?? 0) - (b.evidence[0]?.start ?? 0))
  const at = ordered.findIndex((f) => f.id === current)
  const present = L.SEVERITIES.filter((s) => r.findings.some((f) => f.severity === s))

  return (
    <div className="report">
      <header className="report-head">
        <div><h1>{r.document_name}</h1><p>{r.verdict.text}</p></div>
        <p className="score">{L.READINESS[r.readiness.status]}{r.readiness.score != null && <b>{r.readiness.score}<small> из 100</small></b>}</p>
      </header>
      <nav className="bar">
        <div className="tabs" role="tablist">
          {([['findings', `Замечания ${r.findings.length}`], ['requirements', `Требования ${r.requirements.length}`], ['run', 'Протокол']] as const).map(([k, t]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t}</button>
          ))}
        </div>
        <div className="downloads">Скачать: {(['html', 'md', 'json'] as const).map((f) => <a key={f} href={api.exportUrl(id, f)} download>{{ html: 'HTML', md: 'Markdown', json: 'JSON' }[f]}</a>)}<button className="link" onClick={() => { setTab('findings'); setTimeout(() => window.print()) }}>Печать</button></div>
      </nav>
      {tab === 'findings' && <>
        {r.findings.length > 0
          ? <div className="filter"><label>Показать <select value={severity} onChange={(e) => { setSeverity(e.target.value); setCurrent(null) }}>
            <option value="">все</option>
            {present.map((s) => <option key={s} value={s}>{L.SEVERITY[s].toLowerCase()} серьёзность</option>)}
            {r.findings.some((f) => f.status === 'needs_review') && <option value="needs_review">требуют решения</option>}
          </select></label>
            <span><button className="link" disabled={at === 0 || !list.length} onClick={() => setCurrent(ordered[at < 0 ? ordered.length - 1 : at - 1].id)}>Предыдущее</button> <button className="link" disabled={at === list.length - 1} onClick={() => setCurrent(ordered[at + 1].id)}>Следующее</button>{at >= 0 && ` ${at + 1} из ${list.length}`}</span></div>
          : <p className="filter">{r.status === 'completed' ? 'Замечаний нет.' : 'Выполненные этапы замечаний не дали.'}</p>}
        <Review r={r} list={list} current={current} pick={setCurrent} />
        <section className="print-only"><h2>Замечания</h2>{list.map((f) => <article key={f.id}><h3>{f.id}. {f.title}</h3><p>{L.SEVERITY[f.severity]}, {L.STATUS[f.status].toLowerCase()}</p>{f.evidence.map((e) => <blockquote key={e.start}>{e.quote}</blockquote>)}<FindingBody f={f} /></article>)}</section>
      </>}
      {tab === 'requirements' && <Requirements r={r} open={open} />}
      {tab === 'run' && <Protocol r={r} open={open} />}
    </div>
  )
}

function Checks({ items }: { items: Check[] }) {
  return <table className="checks"><tbody>{items.map((c) => (
    <tr key={c.criterion}><th scope="row">{L.CRITERION[c.criterion]}</th><td className={c.status}>{L.CHECK[c.status]}</td><td>{c.explanation}</td></tr>
  ))}</tbody></table>
}

function Requirements({ r, open }: { r: Report; open: (f: Finding) => void }) {
  return (
    <div className="requirements">{r.requirements.map((x) => {
      const own = r.findings.filter((f) => f.requirement_ids.includes(x.id))
      const bad = x.checks.filter((c) => c.status === 'fail').length
      const none = x.checks.every((c) => c.status === 'not_evaluated')
      return (
        <details key={x.id}>
          <summary><span>{x.source_id ?? x.id}</span><span>{x.summary}</span><span className={bad ? 'fail' : ''}>{none ? 'не оценено' : bad ? L.plural(bad, 'нарушение', 'нарушения', 'нарушений') : own.some((f) => f.status === 'needs_review') ? 'уточнить' : 'без нарушений'}</span></summary>
          <div>
            <p className="quote">{x.text}</p>
            <p className="dim">{x.id}{x.type_confidence ? `, ${L.lowerFirst(L.TYPE[x.requirement_type])}` : ''}</p>
            <Checks items={x.checks} />
            {own.map((f) => <p key={f.id}><button className="link" onClick={() => open(f)}>{f.id} {f.title}</button></p>)}
          </div>
        </details>
      )
    })}</div>
  )
}

function Protocol({ r, open }: { r: Report; open: (f: Finding) => void }) {
  const first = r.verdict.priorities.map((p) => r.findings.find((f) => p.startsWith(f.id + ' '))).filter((f) => f !== undefined)
  return (
    <div className="protocol">
      {first.length > 0 && <section><h2>Исправить в первую очередь</h2><ol>{first.map((f) => <li key={f.id}><button className="link" onClick={() => open(f)}>{f.title}</button>. {f.recommendation}</li>)}</ol></section>}
      <section><h2>Набор требований</h2><Checks items={r.set_checks} /></section>
      <section><h2>Оценка</h2><table className="checks"><tbody>
        {r.readiness.dimensions.map((d) => <tr key={d.id}><th scope="row">{d.title}</th><td>{d.score ?? 'не оценено'}</td><td /></tr>)}
        <tr><th scope="row">Охват критериев</th><td>{r.readiness.coverage}%</td><td /></tr>
      </tbody></table></section>
      <section><h2>Паспорт</h2><table className="checks"><tbody>
        <tr><th scope="row">Дата</th><td colSpan={2}>{new Date(r.analyzed_at).toLocaleString('ru-RU')}</td></tr>
        <tr><th scope="row">Модели</th><td colSpan={2}>{r.model_name}</td></tr>
        <tr><th scope="row">Версия</th><td colSpan={2}>{r.agent_version}</td></tr>
        <tr><th scope="row">Длительность</th><td colSpan={2}>{r.duration_seconds} с</td></tr>
      </tbody></table></section>
      <section><h2>Этапы</h2><table className="checks"><tbody>{r.stages.map((s) => (
        <tr key={s.id}><th scope="row">{s.title}</th><td className={s.status === 'failed' ? 'fail' : ''}>{L.STAGE[s.status]}</td><td>{[s.models.join(', '), s.message].filter(Boolean).join('. ')}</td></tr>
      ))}</tbody></table></section>
      <section><h2>Основания замечаний</h2><table className="checks"><tbody>{r.findings.map((f) => (
        <tr key={f.id}><th scope="row"><button className="link" onClick={() => open(f)}>{f.id}</button> {f.title}</th><td>{Math.round(f.confidence * 100)}%</td><td>{L.SOURCE[f.source]}{f.validation_note && `. ${f.validation_note}`}</td></tr>
      ))}</tbody></table></section>
      {r.rejected_findings.length > 0 && <section><h2>Отклонено при проверке</h2><table className="checks"><tbody>{r.rejected_findings.map((f) => (
        <tr key={f.id}><th scope="row">{f.title}</th><td colSpan={2}>{f.validation_note}</td></tr>
      ))}</tbody></table></section>}
    </div>
  )
}
