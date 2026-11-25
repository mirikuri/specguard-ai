import { Check, Circle, LoaderCircle } from 'lucide-react'
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

  useEffect(() => {
    let stop = false
    let timer = 0
    let misses = 0
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
    return () => { stop = true; clearTimeout(timer) }
  }, [id])

  if (report) return <ReportView id={id} report={report} />
  if (info?.status === 'failed' || (error && !info))
    return (
      <div className="narrow">
        <h1>Анализ не выполнен</h1>
        <p className="error" role="alert">{info?.status === 'failed' ? info.message : error}</p>
        <Link className="primary" to="/">Загрузить документ снова</Link>
      </div>
    )
  return (
    <div className="narrow">
      <h1>{info ? `Проверяем ${info.document_name}` : 'Открываем анализ'}</h1>
      <progress max={100} value={info?.progress ?? 0} aria-label="Ход анализа" />
      <p className="dim" aria-live="polite">{error || (info?.active.length ? stages.filter((s) => info.active.includes(s.id)).map((s) => s.title).join(', ') : info?.message ?? '')}</p>
      <ol className="stages">
        {stages.map((s) => {
          const done = info?.done.includes(s.id), now = info?.active.includes(s.id)
          return (
            <li key={s.id} className={done ? 'done' : now ? 'now' : ''}>
              {done ? <Check aria-label="пройден" /> : now ? <LoaderCircle className="spin" aria-label="выполняется" /> : <Circle aria-label="ожидает" />}{s.title}
            </li>
          )
        })}
      </ol>
      <p className="dim">На бесплатном тарифе Gemini проверка обычно занимает несколько минут. Страницу можно обновлять.</p>
    </div>
  )
}
