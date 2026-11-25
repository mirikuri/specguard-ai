import { Check, Copy, Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../api'
import * as L from '../labels'
import type { Check as CheckT, Finding, Report, Requirement } from '../types'
import { SourceDocument, type Span } from './SourceDocument'

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'] as const

export function ReportView({ id, report: r }: { id: string; report: Report }) {
  const [tab, setTab] = useState<'findings' | 'requirements' | 'run'>('findings')
  const [finding, setFinding] = useState<Finding | null>(r.findings[0] ?? null)
  const [requirement, setRequirement] = useState<Requirement | null>(r.requirements[0] ?? null)
  const open = (f: Finding) => { setFinding(f); setTab('findings') }
  const openReq = (rid: string) => {
    const x = r.requirements.find((q) => q.id === rid)
    if (x) { setRequirement(x); setTab('requirements') }
  }
  const active = useMemo<Span[]>(() => tab === 'requirements'
    ? requirement ? requirement.spans.map(([start, end]) => ({ start, end })) : []
    : finding?.evidence ?? [], [tab, finding, requirement])

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h1>{r.document_name}</h1>
          <p className="verdict">{r.verdict.text}</p>
        </div>
        <div className="downloads">
          {(['html', 'md', 'json'] as const).map((f) => (
            <a key={f} className="secondary" href={api.exportUrl(id, f)} download><Download aria-hidden />{{ html: 'HTML', md: 'Markdown', json: 'JSON' }[f]}</a>
          ))}
        </div>
      </div>
      {r.status !== 'completed' && (
        <div className="notice"><b>Отчёт частичный.</b> Отсутствие замечаний не означает отсутствие дефектов.
          <ul>{r.stages.filter((s) => s.status === 'failed' || s.status === 'partial').map((s) => <li key={s.id}>{s.title}: {s.message}</li>)}</ul>
        </div>
      )}
      <Overview r={r} />
      <div className="tabs" role="tablist">
        {([['findings', `Замечания (${r.findings.length})`], ['requirements', `Требования (${r.requirements.length})`], ['run', 'Набор и прогон']] as const).map(([k, t]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t}</button>
        ))}
      </div>
      {tab === 'run' ? <Run r={r} open={open} /> : (
        <div className="workspace">
          <SourceDocument text={r.document_text} findings={r.findings} active={active} onPick={open} />
          {tab === 'findings' ? <Findings r={r} current={finding} pick={setFinding} openReq={openReq} />
            : <Requirements r={r} current={requirement} pick={setRequirement} open={open} />}
        </div>
      )}
    </div>
  )
}

function Overview({ r }: { r: Report }) {
  const { score, status, coverage, dimensions } = r.readiness
  return (
    <div className="overview">
      <div className="readiness">
        <div className="readiness-title"><strong>{L.READINESS[status]}</strong>{score != null && <span>{score} из 100</span>}</div>
        <div className="scale" role="img" aria-label={score == null ? 'Оценка не рассчитана' : `Оценка ${score} из 100, пороги 70 и 85`}>
          <i style={{ width: '70%' }} className="z0" /><i style={{ width: '15%' }} className="z1" /><i style={{ width: '15%' }} className="z2" />
          {score != null && <b style={{ left: `${score}%` }} />}
        </div>
        <div className="scale-labels"><span>0</span><span style={{ left: '70%' }}>70</span><span style={{ left: '85%' }}>85</span><span style={{ left: '100%' }}>100</span></div>
        <p className="dim">{coverage < 100 ? `Оценено ${coverage}% веса критериев. ` : ''}Методика SpecGuard.</p>
      </div>
      <dl className="dims">{dimensions.map((d) => <div key={d.id}><dt>{d.title}</dt><dd>{d.score ?? 'не оценено'}</dd></div>)}</dl>
      <dl className="dims">
        <div><dt>Требований</dt><dd>{r.summary.requirements_count}</dd></div>
        {SEVERITIES.slice(0, 4).map((s) => <div key={s}><dt className={s}>{L.SEVERITY[s]}</dt><dd>{r.summary[`${s}_count`]}</dd></div>)}
        <div><dt>Требуют решения</dt><dd>{r.summary.needs_review_count}</dd></div>
      </dl>
    </div>
  )
}

function Findings({ r, current, pick, openReq }: { r: Report; current: Finding | null; pick: (f: Finding) => void; openReq: (id: string) => void }) {
  const [severity, setSeverity] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const list = r.findings.filter((f) => (!severity || f.severity === severity) && (!category || f.category === category) && (!status || f.status === status)
    && (!q || `${f.id} ${f.title} ${f.requirement_ids.join(' ')} ${r.requirements.filter((x) => f.requirement_ids.includes(x.id)).map((x) => x.source_id).join(' ')}`.toLowerCase().includes(q.toLowerCase())))
  if (!r.findings.length) return <div className="panel"><p>{r.status === 'completed' ? 'Замечаний нет: ни одна проблема не получила подтверждения в тексте.' : 'Выполненные этапы не дали замечаний. Анализ неполный, повторите его.'}</p></div>
  return (
    <div className="panel">
      <div className="filters">
        <input type="search" placeholder="ID или слово из названия" aria-label="Поиск" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Серьёзность" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">Любая серьёзность</option>{SEVERITIES.map((s) => <option key={s} value={s}>{L.SEVERITY[s]}</option>)}</select>
        <select aria-label="Категория" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">Все категории</option>{[...new Set(r.findings.map((f) => f.category))].map((c) => <option key={c} value={c}>{L.CATEGORY[c]}</option>)}</select>
        <select aria-label="Статус" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Любой статус</option><option value="confirmed">Подтверждено</option><option value="needs_review">Требует решения</option></select>
      </div>
      {list.length === 0 && <p className="dim">Под фильтр ничего не подходит.</p>}
      <ul className="finding-list">
        {list.map((f) => {
          const on = f === current
          return (
            <li key={f.id} className={`${f.severity} ${on ? 'on' : ''}`}>
              <button aria-expanded={on} onClick={() => pick(f)}>
                <span className="finding-id">{f.id}</span><span className="finding-title">{f.title}</span>
                <span className="finding-meta"><b className={f.severity}>{L.SEVERITY[f.severity]}</b>, {L.lowerFirst(L.CATEGORY[f.category])}{f.status === 'needs_review' && <em>Требует решения</em>}</span>
              </button>
              {on && <FindingBody f={f} openReq={openReq} />}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function FindingBody({ f, openReq }: { f: Finding; openReq: (id: string) => void }) {
  return (
    <div className="finding-body">
      {f.evidence.map((e) => (
        <figure key={`${e.start}-${e.end}`}><blockquote>{e.quote}</blockquote>
          <figcaption>{e.requirement_id ? <button className="link" onClick={() => openReq(e.requirement_id!)}>{e.requirement_id}</button> : 'Вне требований'}, {e.section.split(' / ').slice(-2).join(', ')}{e.page ? `, страница ${e.page}` : ''}</figcaption></figure>
      ))}
      <h3>Почему это проблема</h3><p>{f.explanation}</p>
      <h3>Последствия</h3><p>{f.impact}</p>
      <h3>Рекомендация</h3><p>{f.recommendation}</p>
      {f.fix && <div className="fix">
        <h3>Вариант исправления</h3><p className="fix-text">{f.fix.proposed_text}</p>
        <p>{f.fix.changes} {f.fix.rationale}</p>
        <h3>Критерий приёмки</h3><p>{f.fix.acceptance_criteria}</p>
        {f.fix.clarification_required && <><h3>Вопрос аналитику</h3><p>{f.fix.clarification_question}</p></>}
      </div>}
      <CopyButton text={f.fix?.proposed_text || f.recommendation} label={f.fix ? 'Скопировать исправление' : 'Скопировать рекомендацию'} />
      <p className="dim">Источник: {L.SOURCE[f.source]}. Уверенность {Math.round(f.confidence * 100)}%. {f.validation_note}</p>
    </div>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState('')
  return (
    <button className="secondary" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setState('Скопировано') } catch { setState('Не удалось скопировать') }
      setTimeout(() => setState(''), 2000)
    }}>{state === 'Скопировано' ? <Check aria-hidden /> : <Copy aria-hidden />}{state || label}</button>
  )
}

function Checks({ items }: { items: CheckT[] }) {
  return <table className="checks"><tbody>{items.map((c) => (
    <tr key={c.criterion}><th scope="row">{L.CRITERION[c.criterion]}</th><td className={c.status}>{L.CHECK[c.status]}</td><td>{c.explanation}</td></tr>
  ))}</tbody></table>
}

function Requirements({ r, current, pick, open }: { r: Report; current: Requirement | null; pick: (x: Requirement) => void; open: (f: Finding) => void }) {
  const [q, setQ] = useState('')
  const list = r.requirements.filter((x) => `${x.id} ${x.source_id ?? ''} ${x.summary} ${x.text}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="panel">
      <div className="filters"><input type="search" placeholder="ID или текст требования" aria-label="Поиск требования" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      {list.length === 0 && <p className="dim">Требований с таким текстом нет.</p>}
      <ul className="finding-list">
        {list.map((x) => {
          const on = x === current
          const own = r.findings.filter((f) => f.requirement_ids.includes(x.id))
          const bad = x.checks.filter((c) => c.status === 'fail').length
          const none = x.checks.every((c) => c.status === 'not_evaluated')
          return (
            <li key={x.id} className={on ? 'on' : ''}>
              <button aria-expanded={on} onClick={() => pick(x)}>
                <span className="finding-id">{x.id}</span><span className="finding-title">{x.summary}</span>
                <span className="finding-meta">{x.source_id ? `В документе: ${x.source_id}. ` : ''}{x.type_confidence ? L.TYPE[x.requirement_type] : 'Тип не определён'}.{' '}
                  {none ? 'Критерии не оценены' : bad ? <b className="high">Нарушено критериев: {bad}</b> : 'Без нарушений'}</span>
              </button>
              {on && <div className="finding-body">
                <blockquote>{x.text}</blockquote>
                <Checks items={x.checks} />
                {own.length > 0 && <><h3>Связанные замечания</h3><ul className="plain">{own.map((f) => <li key={f.id}><button className="link" onClick={() => open(f)}>{f.id} {f.title}</button></li>)}</ul></>}
              </div>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Run({ r, open }: { r: Report; open: (f: Finding) => void }) {
  return (
    <div className="run">
      <section><h2>Что исправить в первую очередь</h2>
        {r.verdict.priorities.length ? <ol>{r.verdict.priorities.map((p) => {
          const f = r.findings.find((x) => p.startsWith(x.id + ' '))
          return <li key={p}>{f ? <><button className="link" onClick={() => open(f)}>{f.id} {f.title}</button><br />{f.recommendation}</> : p}</li>
        })}</ol> : <p>Подтверждённых замечаний нет.</p>}</section>
      <section><h2>Проверка набора требований</h2><Checks items={r.set_checks} /></section>
      <section><h2>Паспорт прогона</h2>
        <table className="checks"><tbody>
          <tr><th scope="row">Дата</th><td>{new Date(r.analyzed_at).toLocaleString('ru-RU')}</td></tr>
          <tr><th scope="row">Модель</th><td>{r.model_name}</td></tr>
          <tr><th scope="row">Версия агента</th><td>{r.agent_version}</td></tr>
          <tr><th scope="row">Длительность</th><td>{r.duration_seconds} с</td></tr>
        </tbody></table>
        <table className="checks"><tbody>{r.stages.map((s) => <tr key={s.id}><th scope="row">{s.title}</th><td className={s.status === 'failed' ? 'fail' : ''}>{L.STAGE[s.status]}</td><td>{s.models.join(', ') || 'без модели'}</td><td>{s.message}</td></tr>)}</tbody></table></section>
      {r.rejected_findings.length > 0 && <section><h2>Отклонено при проверке доказательств</h2>
        <table className="checks"><tbody>{r.rejected_findings.map((f) => <tr key={f.id}><th scope="row">{f.title}</th><td>{f.validation_note}</td></tr>)}</tbody></table></section>}
    </div>
  )
}
