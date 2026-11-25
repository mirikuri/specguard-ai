import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './styles.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import { Backdrop } from './components/Art'
import { AnalysisPage } from './pages/AnalysisPage'
import { HomePage } from './pages/HomePage'
import { HelpPage } from './pages/HelpPage'

function NotFound() {
  return <div className="page"><div className="panel pad"><h1>Страница не найдена</h1><Link className="btn" to="/">К проверкам</Link></div></div>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Backdrop />
      <header className="topbar"><div>
        <Link to="/" className="brand"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 3.5H17V10.2C17 14.1 13.9 16.9 10 18C6.1 16.9 3 14.1 3 10.2V3.5Z" /><path d="M7.5 8.5L9.3 10.3L12.8 6.8" /></svg>SpecGuard</Link>
        <nav><NavLink to="/" end>Проверки</NavLink><NavLink to="/help">Как это работает</NavLink></nav>
      </div></header>
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/analysis/:id" element={<AnalysisPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </BrowserRouter>
  </StrictMode>,
)
