import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { ReportView } from '../components/ReportView'
import type { AnalysisInfo, Health, Report } from '../types'

export function AnalysisPage() {
  const { id = '' } = useParams()
  const [info, setInfo] = useState<AnalysisInfo | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [stages, setStages] = useState<Health['stages']>([])
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    let stop = false, timer = 0, misses = 0
    setInfo(null); setReport(null); setError('')
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
      timer = window.setTimeout(poll, 1500)
    }
    poll()
    const clock = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { stop = true; clearTimeout(timer); clearInterval(clock) }
  }, [id])

  if (report) return <ReportView id={id} report={report} />
  if (info?.status === 'failed' || (error && !info))
    return (
      <div className="page">
        <h1>Проверка не выполнена</h1>
        <p className="error" role="alert">{info?.status === 'failed' ? info.message : error}</p>
        <p><Link to="/">К проверкам</Link></p>
      </div>
    )
  const seconds = info ? Math.max(0, Math.floor((now - Date.parse(info.created_at)) / 1000)) : 0
  return (
    <div className="page">
      <h1>{info?.document_name ?? 'Проверка'}</h1>
      <p className="elapsed">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</p>
      {error && <p className="error" role="alert">{error}</p>}
      <ol className="stages" aria-live="polite">
        {stages.map((s) => {
          const done = info?.done.includes(s.id), active = info?.active.includes(s.id)
          return <li key={s.id} className={done ? 'done' : active ? 'now' : ''}>{s.title}<span>{done ? 'готово' : active ? 'выполняется' : ''}</span></li>
        })}
      </ol>
    </div>
  )
}
