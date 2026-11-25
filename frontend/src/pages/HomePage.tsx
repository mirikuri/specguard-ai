import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { READINESS } from '../labels'
import type { AnalysisInfo, Health } from '../types'

const OPTIONS = [
  ['atomic_analysis', 'Каждое требование'],
  ['consistency_analysis', 'Противоречия'],
  ['fintech_analysis', 'Деньги и транзакции'],
  ['security_analysis', 'Безопасность'],
  ['generate_fixes', 'Варианты исправлений'],
] as const
const MAX = 10 * 1024 * 1024
const STATE: Record<string, string> = { queued: 'В очереди', running: 'Выполняется', failed: 'Ошибка' }

export function HomePage() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [list, setList] = useState<AnalysisInfo[]>([])
  const [asking, setAsking] = useState('')
  const [options, setOptions] = useState<Record<string, boolean>>(Object.fromEntries(OPTIONS.map(([k]) => [k, true])))
  const offline = health?.model_ready === false

  useEffect(() => {
    Promise.all([api.health(), api.recent()])
      .then(([h, r]) => { setHealth(h); setList(r) })
      .catch((e: Error) => setError(e.message))
  }, [])

  function pick(f?: File) {
    if (!f) return
    if (!/\.(md|markdown|txt|pdf)$/i.test(f.name)) return setError('Поддерживаются PDF и Markdown.')
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
      const { analysis_id } = await api.start({ document_id, options, rules_only: offline })
      navigate(`/analysis/${analysis_id}`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  async function remove(id: string) {
    try {
      await api.remove(id)
      setList((x) => x.filter((a) => a.analysis_id !== id))
    } catch (e) { setError((e as Error).message) }
    setAsking('')
  }

  return (
    <div className="page">
      <h1>Проверка требований</h1>
      <div className={`drop ${over ? 'over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}>
        <input ref={input} type="file" hidden accept=".md,.markdown,.txt,.pdf"
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
        <span className="drop-name">{file ? file.name : 'PDF или Markdown, до 10 МБ'}</span>
        <button className="plain-btn" onClick={() => input.current?.click()}>{file ? 'Заменить' : 'Выбрать файл'}</button>
        <button className="primary" disabled={!file || busy || !health} onClick={start}>{busy ? 'Загрузка…' : offline ? 'Проверить по правилам' : 'Проверить'}</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {offline && <p className="notice">Модель не подключена. Проверка по правилам даст частичный отчёт.</p>}
      <details className="options">
        <summary>Параметры</summary>
        {OPTIONS.map(([key, title]) => (
          <label key={key}><input type="checkbox" checked={options[key]} onChange={(e) => setOptions({ ...options, [key]: e.target.checked })} />{title}</label>
        ))}
      </details>
      {health && !offline && <p className="dim">Текст документа передаётся сторонней модели через OpenRouter.</p>}

      {list.length > 0 && <section className="history">
        <h2>Проверки</h2>
        <table>
          <thead><tr><th>Документ</th><th>Дата</th><th>Вывод</th><th className="num">Замечаний</th><th><span className="sr">Действие</span></th></tr></thead>
          <tbody>{list.map((a) => (
            <tr key={a.analysis_id}>
              <td data-label="Документ"><Link to={`/analysis/${a.analysis_id}`}>{a.document_name}</Link></td>
              <td data-label="Дата">{new Date(a.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</td>
              <td data-label="Вывод">{a.readiness_status ? READINESS[a.readiness_status] + (a.score != null ? `, ${a.score}` : '') : STATE[a.status]}{a.status === 'partial' && ' (частично)'}</td>
              <td data-label="Замечаний" className="num">{a.findings_count ?? '–'}</td>
              <td className="act">{!['queued', 'running'].includes(a.status) && (asking === a.analysis_id
                ? <><button className="link danger" onClick={() => remove(a.analysis_id)}>Удалить</button> <button className="link" onClick={() => setAsking('')}>Отмена</button></>
                : <button className="link" aria-label={`Удалить проверку ${a.document_name}`} onClick={() => setAsking(a.analysis_id)}>Удалить</button>)}</td>
            </tr>
          ))}</tbody>
        </table>
      </section>}
    </div>
  )
}
