import { FileSearch, FileUp, PenLine, Quote, Scale, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Mosaic } from '../components/Art'

const STEPS = [
  [FileUp, 'Загрузите документ', 'PDF или Markdown до 10 МБ. Отметьте, что проверить.'],
  [FileSearch, 'Подождите', 'Обычно несколько минут. Страницу можно закрыть, отчёт сохранится.'],
  [PenLine, 'Исправьте', 'Откройте замечание, посмотрите место в тексте и возьмите готовую формулировку.'],
] as const
const FACTS = [
  [Quote, 'Почему замечаниям можно верить', 'У каждого есть точная цитата: программа сама находит её в документе, а без цитаты замечание отбрасывается. Затем вторая проверка пытается его опровергнуть. Спорное получает пометку «Требует решения», и его смотрит аналитик.'],
  [FileSearch, 'Что ищет проверка', 'Противоречия, пропущенные условия, непроверяемые формулировки, ошибки в описании API, пробелы в денежной логике и безопасности. Каждое требование оценивается по девяти критериям ISO/IEC/IEEE 29148, весь набор по пяти.'],
  [Scale, 'Как считается оценка', 'От 0 до 100. От 85 документ готов к разработке, от 70 готов после исправлений, ниже не готов. Оценку снижают только подтверждённые замечания.'],
  [ShieldAlert, 'Что происходит с документом', 'Текст отправляется внешним ИИ-моделям через OpenRouter, и поставщики могут сохранять запросы. Документы с банковской или коммерческой тайной загружать нельзя. Отчёт хранится на сервере, пока вы его не удалите.'],
] as const

export function HelpPage() {
  return (
    <div className="page help">
      <section className="panel masthead"><div><h1>Как это работает</h1><p>Три шага от документа до списка исправлений.</p><Link className="btn primary" to="/">Начать проверку</Link></div><Mosaic seed="help" cols={8} rows={3} className="cover" /></section>
      <ol className="panel three">{STEPS.map(([Icon, t, d]) => <li key={t}><Icon aria-hidden /><h2>{t}</h2><p>{d}</p></li>)}</ol>
      <div className="facts">{FACTS.map(([Icon, t, d]) => <section key={t} className="panel pad"><Icon aria-hidden /><h2>{t}</h2><p>{d}</p></section>)}</div>
    </div>
  )
}
