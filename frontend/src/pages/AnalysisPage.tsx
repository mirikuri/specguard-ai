import { Check, Circle, CircleAlert, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { Mosaic } from '../components/Art'
import { ReportView } from '../components/ReportView'
import type { AnalysisInfo, Health, Report } from '../types'

const HINT: Record<string, string> = {
  requirements_extraction: 'Делим документ на отдельные требования',
  structure_rules: 'Ищем явные ошибки без ИИ',
  atomic_analysis: 'Оцениваем каждое требование по 9 критериям',
  consistency_analysis: 'Сравниваем требования между собой',
  fintech_analysis: 'Проверяем деньги, сбои и безопасность',
  evidence_validation: 'Вторая модель пытается опровергнуть замечания',
  fix_generation: 'Пишем формулировки исправлений',
  report_generation: 'Собираем отчёт',
}
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export function AnalysisPage() {
  const { id = '' } = useParams()
  const [info, setInfo] = useState<AnalysisInfo | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [stages, setStages] = useState<Health['stages']>([])
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now())
  const [stopping, setStopping] = useState(false)

  useEffect(() => {
    let stop = false, timer = 0, misses = 0
    setInfo(null); setReport(null); setError(''); setStopping(false)
    api.health().then((h) => !stop && setStages(h.stages)).catch(() => {})
    async function poll() {
      try {
        const next = await api.status(id)
        if (stop) return
        misses = 0
        setInfo(next)
        setError('')
        if (next.status === 'completed' || next.status === 'partial') {
          const r = await api.report(id)
          if (!stop) setReport(r)
          return
        }
        if (next.status === 'failed') return
      } catch (e) {
        if (stop) return
        setError((e as Error).message)
        if (++misses > 5 || /не найден/.test((e as Error).message)) return
      }
      timer = window.setTimeout(poll, 1000)
    }
    poll()
    const tick = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { stop = true; clearTimeout(timer); clearInterval(tick) }
  }, [id])

  if (report) return <ReportView id={id} report={report} />
  const events = info?.events ?? []
  const since = (iso?: string) => iso ? Math.max(0, (now - Date.parse(iso)) / 1000) : 0
  if (info?.status === 'failed' || (error && !info))
    return (
      <div className="page"><div className="panel pad fail-box">
        <CircleAlert aria-hidden />
        <h1>{info?.message.startsWith('Отменено') ? 'Проверка отменена' : 'Проверка не выполнена'}</h1>
        {!info?.message.startsWith('Отменено') && <p role="alert">{info?.message ?? error}</p>}
        <p className="dim">{info ? 'Отчёт не создан. Загрузите документ ещё раз, чтобы повторить.' : 'Возможно, проверка была удалена.'}</p>
        <Link className="btn primary" to="/">К проверкам</Link>
      </div></div>
    )
  const found = events.filter((e) => e.kind === 'finding')
  const log = events.filter((e) => e.kind !== 'finding')
  return (
    <div className="page progress-page">
      <section className="panel pad progress-head">
        <div><h1>{info?.document_name ?? 'Открываем проверку'}</h1>
          <p aria-live="polite">{info?.active.map((s) => HINT[s]).filter(Boolean).join('. ') || info?.message || 'Загрузка…'}</p></div>
        <div className="progress-side"><span className="clock">{clock(since(info?.created_at))}</span>
          {info && <button className="btn" disabled={stopping} onClick={() => { setStopping(true); api.cancel(id).catch((e: Error) => { setError(e.message); setStopping(false) }) }}>{stopping ? 'Останавливаем…' : 'Отменить'}</button>}</div>
        <progress max={100} value={info?.progress ?? 0} aria-label="Ход проверки" />
        {error && <p className="msg bad" role="alert">{error} Пробуем подключиться снова.</p>}
      </section>
      <section className="panel build"><Mosaic seed={id} cols={16} rows={2} shown={(info?.progress ?? 0) / 100} className="cover" /></section>
      <section className="panel">
        <header className="panel-head"><h2>Этапы</h2><span className="dim">{info?.done.length ?? 0} из {stages.length}</span></header>
        <ol className="steps">{stages.map((s) => {
          const done = info?.done.includes(s.id), active = info?.active.includes(s.id)
          const from = info?.started?.[s.id], to = info?.finished?.[s.id]
          return <li key={s.id} className={done ? 'done' : active ? 'now' : ''}>
            {done ? <Check aria-label="готово" /> : active ? <LoaderCircle className="spin" aria-label="выполняется" /> : <Circle aria-label="ожидает" />}
            <span><b>{s.title}</b><span>{HINT[s.id]}</span></span>
            <time>{done && from && to ? clock((Date.parse(to) - Date.parse(from)) / 1000) : active ? clock(since(from)) : ''}</time></li>
        })}</ol>
      </section>
      <section className="panel">
        <header className="panel-head"><h2>Что происходит</h2></header>
        <ol className="log">{[...log].reverse().map((e, i) => <li key={log.length - i} className={e.kind}><time>{clock(Math.max(0, (Date.parse(e.time) - Date.parse(info!.created_at)) / 1000))}</time>{e.text}</li>)}
          {log.length === 0 && <li>Ждём первый шаг…</li>}</ol>
      </section>
      <section className="panel">
        <header className="panel-head"><h2>Найдено</h2><span className="dim">{found.length}, до перепроверки</span></header>
        {found.length ? <ol className="found">{found.map((e, i) => <li key={i}>{e.text}</li>)}</ol>
          : <p className="pad dim">Замечания появятся здесь по мере проверки. Часть из них отсеется при перепроверке.</p>}
      </section>
      <p className="panel panel-foot wide">Страницу можно закрыть: проверка продолжится, отчёт появится в списке.</p>
    </div>
  )
}
