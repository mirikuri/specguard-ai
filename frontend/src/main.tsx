import '@fontsource-variable/golos-text'
import '@fontsource/pt-serif/cyrillic-400.css'
import '@fontsource/pt-serif/latin-400.css'
import './styles.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { AnalysisPage } from './pages/AnalysisPage'
import { HomePage } from './pages/HomePage'

function NotFound() {
  return <div className="narrow"><h1>Страница не найдена</h1><p><Link to="/">Проверить документ</Link></p></div>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <header className="topbar">
        <Link to="/" className="brand">SpecGuard AI</Link>
        <Link to="/" className="topbar-link">Новая проверка</Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/analysis/:id" element={<AnalysisPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </BrowserRouter>
  </StrictMode>,
)
