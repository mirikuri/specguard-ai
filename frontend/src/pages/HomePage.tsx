import { Banknote, FileText, FileUp, GitCompareArrows, ListChecks, PenLine, SearchCheck, ShieldAlert, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Mosaic } from '../components/Art'
import { plural, READINESS } from '../labels'
import type { AnalysisInfo, Health } from '../types'

const OPTIONS = [
  ['atomic_analysis', 'Качество каждого требования', 'Однозначность, полнота, проверяемость и ещё 6 критериев', ListChecks],
  ['consistency_analysis', 'Противоречия', 'Расхождения между требованиями и критериями приёмки', GitCompareArrows],
  ['fintech_analysis', 'Деньги и транзакции', 'Возвраты, повторы операций, округление, часовые пояса', Banknote],
  ['security_analysis', 'Безопасность', 'Доступ, персональные данные, журналирование', ShieldCheck],
  ['generate_fixes', 'Варианты исправлений', 'Готовая формулировка и вопрос аналитику к каждому замечанию', PenLine],
] as const
const MAX = 10 * 1024 * 1024

function size(n: number) {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} КБ` : `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`
}

export function HomePage() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [list, setList] = useState<AnalysisInfo[] | null>(null)
  const [asking, setAsking] = useState('')
  const [options, setOptions] = useState<Record<string, boolean>>(Object.fromEntries(OPTIONS.map(([k]) => [k, true])))
  const [cover] = useState(() => String(Math.random()))
  const offline = health?.model_ready === false
  const checks = OPTIONS.slice(0, 4).some(([k]) => options[k])

  useEffect(() => {
    let stop = false
    const load = () => api.recent().then((r) => !stop && setList(r)).catch(() => {})
    api.health().then((h) => !stop && setHealth(h)).catch((e: Error) => !stop && setError(e.message))
    load()
    const t = window.setInterval(load, 4000)
    return () => { stop = true; clearInterval(t) }
  }, [])

  function pick(f?: File) {
    if (!f) return
    if (!/\.(md|markdown|txt|pdf)$/i.test(f.name)) return setError(`Файл «${f.name}» не подходит. Нужен PDF или Markdown.`)
    if (f.size > MAX) return setError(`Файл «${f.name}» больше 10 МБ. Разделите документ на части.`)
    setError('')
    setFile(f)
  }

  async function sample() {
    try {
      const r = await fetch('/primer-tz.md')
      if (!r.ok) throw new Error()
      pick(new File([await r.blob()], 'primer-tz.md', { type: 'text/markdown' }))
    } catch { setError('Пример не загрузился. Выберите свой файл.') }
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
      setList((x) => x && x.filter((a) => a.analysis_id !== id))
    } catch (e) { setError((e as Error).message) }
    setAsking('')
  }

  return (
    <div className="page home">
      <section className="panel masthead">
        <div><h1>Найдите ошибки в ТЗ до начала разработки</h1>
          <p>Загрузите документ и получите список проблем с цитатами и готовыми исправлениями.</p>
          <ol><li><FileUp aria-hidden />Загрузите</li><li><SearchCheck aria-hidden />Проверьте</li><li><PenLine aria-hidden />Исправьте</li></ol></div>
        <Mosaic seed={cover} cols={8} rows={3} className="cover" />
      </section>
      <section className="panel">
        <header className="panel-head"><h2>Новая проверка</h2></header>
        <div className="pad">
          <div className={`drop ${over ? 'over' : ''} ${file ? 'has' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}>
            <input ref={input} type="file" hidden accept=".md,.markdown,.txt,.pdf" aria-label="Документ"
              onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
            {file ? <FileText aria-hidden /> : <Upload aria-hidden />}
            <div><b>{file ? file.name : 'Перетащите техническое задание'}</b><span>{file ? size(file.size) : 'PDF или Markdown, до 10 МБ'}</span></div>
            <button className="btn strong" onClick={() => input.current?.click()}>{file ? 'Заменить' : 'Выбрать файл'}</button>
            {!file && <p className="sample">Нет файла под рукой? <button className="link" onClick={sample}>Взять пример ТЗ</button></p>}
          </div>
          <fieldset>
            <legend>Что проверить <span>Выбрано {OPTIONS.filter(([k]) => options[k]).length} из {OPTIONS.length}</span></legend>
            {OPTIONS.map(([key, title, text, Icon]) => (
              <label key={key} className="option"><input type="checkbox" checked={options[key]} onChange={(e) => setOptions({ ...options, [key]: e.target.checked })} /><span><b>{title}</b>{text}</span><Icon aria-hidden /></label>
            ))}
          </fieldset>
          {offline && <p className="msg warn">ИИ-модель не подключена. Сработают только программные правила, отчёт будет неполным.</p>}
          {error && <p className="msg bad" role="alert">{error}</p>}
          <div className="start">
            <button className="btn primary big" disabled={!file || busy || !health || (!checks && !offline)} onClick={start}>{busy ? 'Загружаем документ…' : 'Начать проверку'}</button>
            <span className="dim">{!file ? 'Сначала выберите документ' : !checks && !offline ? 'Отметьте хотя бы одну проверку' : 'Обычно занимает несколько минут'}</span>
          </div>
        </div>
        <p className="panel-foot"><ShieldAlert aria-hidden /><span>Не загружайте документы с банковской тайной: текст обрабатывает внешний ИИ. <Link to="/help">Подробнее</Link></span></p>
      </section>

      <section className="panel">
        <header className="panel-head"><h2>Мои проверки</h2>{!!list?.length && <span className="dim">{list.length}</span>}</header>
        {list === null ? <p className="pad dim">Загрузка…</p> : list.length === 0 ? (
          <div className="pad empty"><Mosaic seed="empty" cols={3} rows={2} className="empty-art" /><b>Проверок пока нет</b><span>После первой проверки отчёт появится здесь: оценка, число замечаний и ссылка на документ.</span></div>
        ) : <ul className="runs">{list.map((a) => {
          const live = a.status === 'queued' || a.status === 'running'
          return (
            <li key={a.analysis_id}>
              <Link to={`/analysis/${a.analysis_id}`}>
                <Mosaic seed={a.analysis_id} cols={2} rows={2} className="thumb" />
                                <span className="run-main"><b>{a.document_name}</b>
                  <span>{live ? a.message : a.status === 'failed' ? a.message : READINESS[a.readiness_status!]}{a.status === 'partial' && '. Отчёт неполный'}</span>
                  <span className="dim">{new Date(a.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}{a.findings_count != null && `, ${plural(a.findings_count, 'замечание', 'замечания', 'замечаний')}`}</span></span>
                <span className={`score ${a.readiness_status ?? a.status}`}>{live ? `${a.progress}%` : a.score ?? '–'}</span>
              </Link>
              {!live && (asking === a.analysis_id
                ? <span className="ask"><button className="btn danger" onClick={() => remove(a.analysis_id)}>Удалить</button><button className="btn" onClick={() => setAsking('')}>Отмена</button></span>
                : <button className="icon" aria-label={`Удалить проверку ${a.document_name}`} title="Удалить" onClick={() => setAsking(a.analysis_id)}><Trash2 aria-hidden /></button>)}
            </li>
          )
        })}</ul>}
      </section>
    </div>
  )
}
