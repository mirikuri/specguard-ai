import { FileText, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { plural, READINESS } from '../labels'
import type { AnalysisInfo, Health } from '../types'

const OPTIONS = [
  ['atomic_analysis', 'Каждое требование отдельно'],
  ['consistency_analysis', 'Противоречия и связи'],
  ['fintech_analysis', 'Деньги и транзакции'],
  ['security_analysis', 'Безопасность'],
  ['generate_fixes', 'Варианты исправлений'],
] as const
const MAX = 10 * 1024 * 1024
const STATE: Record<string, string> = { queued: 'в очереди', running: 'выполняется', failed: 'ошибка' }

export function HomePage() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [recent, setRecent] = useState<AnalysisInfo[]>([])
  const [options, setOptions] = useState<Record<string, boolean>>(Object.fromEntries(OPTIONS.map(([k]) => [k, true])))

  useEffect(() => {
    Promise.all([api.health(), api.recent()])
      .then(([h, r]) => { setHealth(h); setRecent(r) })
      .catch((e: Error) => setError(e.message))
  }, [])

  function pick(f?: File) {
    if (!f) return
    if (!/\.(md|markdown|txt|pdf)$/i.test(f.name)) return setError('Этот формат не поддерживается. Выберите файл Markdown или PDF.')
    if (f.size > MAX) return setError('Файл больше 10 МБ.')
    setError('')
    setFile(f)
  }

  async function start() {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const { document_id } = await api.upload(file)
      const { analysis_id } = await api.start({ document_id, options, rules_only: health?.model_ready === false })
      navigate(`/analysis/${analysis_id}`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="home">
      <section>
        <h1>Проверьте техническое задание до начала разработки</h1>
        <p className="lead">Система найдёт противоречия, пропуски и двусмысленности, а к каждому замечанию приложит точную цитату из документа.</p>
        <div className={`drop ${over ? 'over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}>
          <input ref={input} type="file" hidden accept=".md,.markdown,.txt,.pdf"
            onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
          {file ? <>
            <FileText aria-hidden />
            <div className="drop-file"><b>{file.name}</b><span>{(file.size / 1024).toFixed(1)} КБ</span></div>
            <button className="link" onClick={() => input.current?.click()}>Заменить файл</button>
          </> : <>
            <Upload aria-hidden />
            <div className="drop-file"><b>Перетащите сюда документ</b><span>Markdown или PDF до 10 МБ</span></div>
            <button className="secondary" onClick={() => input.current?.click()}>Выбрать файл</button>
          </>}
        </div>
        <fieldset>
          <legend>Что проверить, профиль «Финтех»</legend>
          {OPTIONS.map(([key, title]) => (
            <label key={key}><input type="checkbox" checked={options[key]} onChange={(e) => setOptions({ ...options, [key]: e.target.checked })} />{title}</label>
          ))}
        </fieldset>
        {health && !health.model_ready && (
          <p className="notice">Модель не подключена: в файле .env нет GEMINI_API_KEY. Доступны только программные правила, отчёт будет частичным.</p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={!file || busy} onClick={start}>
          {busy ? 'Загружаем документ…' : health?.model_ready === false ? 'Проверить по правилам' : 'Начать анализ'}
        </button>
        {health && <p className="dim">Основная модель: {health.model}. Текст документа отправляется в Gemini API{health.model_ready ? '' : ' только при подключённой модели'}.</p>}
      </section>
      <aside>
        <h2>Последние проверки</h2>
        {recent.length === 0 ? <p className="dim">Здесь появятся отчёты. Они хранятся, пока запущен сервер.</p> : (
          <ul className="recent">
            {recent.map((a) => (
              <li key={a.analysis_id}><Link to={`/analysis/${a.analysis_id}`}>
                <b>{a.document_name}</b>
                <span>{a.readiness_status
                  ? `${READINESS[a.readiness_status]}${a.score != null ? `, ${a.score} из 100` : ''}. ${plural(a.findings_count ?? 0, 'замечание', 'замечания', 'замечаний')}`
                  : STATE[a.status]}</span>
                <time>{new Date(a.created_at).toLocaleString('ru-RU')}</time>
              </Link></li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  )
}
