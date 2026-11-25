import type { AnalysisInfo, Health, Report } from './types'

const BASE = '/api/v1'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(BASE + path, init)
  } catch {
    throw new Error('Сервер не отвечает.')
  }
  if (r.status === 204) return undefined as T
  const body = await r.json().catch(() => null)
  if (!r.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `Сервер вернул ошибку ${r.status}.`)
  return body as T
}

export const api = {
  health: () => call<Health>('/health'),
  recent: () => call<AnalysisInfo[]>('/analyses'),
  status: (id: string) => call<AnalysisInfo>(`/analyses/${id}`),
  report: (id: string) => call<Report>(`/analyses/${id}/report`),
  remove: (id: string) => call<void>(`/analyses/${id}`, { method: 'DELETE' }),
  cancel: (id: string) => call<object>(`/analyses/${id}/cancel`, { method: 'POST' }),
  exportUrl: (id: string, format: string) => `${BASE}/analyses/${id}/export?format=${format}`,
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return call<{ document_id: string }>('/documents', { method: 'POST', body: form })
  },
  start: (body: object) =>
    call<{ analysis_id: string }>('/analyses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
}
