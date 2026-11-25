import { memo, useMemo, type ReactNode } from 'react'

const INK = '#121417', PAPER = '#ffffff', GREY = '#dcdcd5'

export function rng(seed: string) {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return () => {
    h = (h + 0x6d2b79f5) | 0
    let t = Math.imul(h ^ (h >>> 15), 1 | h)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const range = (n: number) => Array.from({ length: n }, (_, i) => i)

/** Клетка 100×100. */
const TILES: ((r: () => number) => ReactNode)[] = [
  () => <path d="M0 0H100A100 100 0 0 1 0 100Z" fill={INK} />,
  () => range(5).map((i) => <circle key={i} cx="0" cy="0" r={18 + i * 19} fill="none" stroke={INK} strokeWidth="8" />),
  () => <path d="M0 50A50 50 0 0 1 100 50Z M0 100A50 50 0 0 1 100 100Z" fill={INK} />,
  () => range(7).map((i) => <rect key={i} x={i * 15} width="7.5" height="100" fill={INK} />),
  () => range(11).map((i) => <path key={i} d={`M${i * 20 - 100} 100L${i * 20} 0`} stroke={INK} strokeWidth="7" />),
  () => range(25).map((i) => <circle key={i} cx={10 + (i % 5) * 20} cy={10 + Math.floor(i / 5) * 20} r={1.5 + (i % 5) * 1.7} fill={INK} />),
  () => <><circle cx="50" cy="50" r="50" fill={INK} /><circle cx="50" cy="50" r="22" fill={PAPER} /></>,
  () => range(8).map((i) => <rect key={i} x={((i % 2) * 2 + (Math.floor(i / 2) % 2)) * 25} y={Math.floor(i / 2) * 25} width="25" height="25" fill={INK} />),
  () => <path d="M0 100L50 0L100 100Z" fill={INK} />,
  () => range(6).map((i) => <path key={i} d={`M0 ${10 + i * 17}Q25 ${-6 + i * 17} 50 ${10 + i * 17}T100 ${10 + i * 17}`} fill="none" stroke={INK} strokeWidth="5" />),
  () => <><rect width="100" height="100" fill={INK} /><circle cx="50" cy="50" r="30" fill="none" stroke={PAPER} strokeWidth="6" /><path d="M0 50H100M50 0V100" stroke={PAPER} strokeWidth="3" /></>,
  () => <><rect width="100" height="100" fill={GREY} /><path d="M50 0A50 50 0 0 1 50 100Z" fill={INK} /></>,
  () => <path d="M50 0C60 40 60 40 100 50C60 60 60 60 50 100C40 60 40 60 0 50C40 40 40 40 50 0Z" fill={INK} />,
  (r) => range(9).map((i) => <rect key={i} x={(i % 3) * 34 + 2} y={Math.floor(i / 3) * 34 + 2} width="28" height="28" fill={r() > .5 ? INK : 'none'} stroke={INK} strokeWidth="3" />),
  () => <><path d="M0 50Q50 -10 100 50Q50 110 0 50Z" fill="none" stroke={INK} strokeWidth="6" /><circle cx="50" cy="50" r="20" fill={INK} /></>,
]

/** Мозаика из случайных фигур. shown < 1 открывает её постепенно. */
export const Mosaic = memo(function Mosaic({ seed, cols, rows, shown = 1, className }: { seed: string; cols: number; rows: number; shown?: number; className?: string }) {
  const tiles = useMemo(() => {
    const r = rng(seed)
    const bag: number[] = [] // фигура не повторяется, пока не использованы остальные
    const list = range(cols * rows).map((i) => {
      if (!bag.length) bag.push(...range(TILES.length))
      const k = bag.splice(Math.floor(r() * bag.length), 1)[0]
      return { i, turn: Math.floor(r() * 4) * 90, body: TILES[k](r), order: r() }
    })
    const ranks = [...list].sort((a, b) => a.order - b.order).map((t) => t.i)
    return list.map((t) => ({ ...t, rank: ranks.indexOf(t.i) }))
  }, [seed, cols, rows])
  const count = Math.round(shown * cols * rows)
  return (
    <svg className={className} viewBox={`0 0 ${cols * 100} ${rows * 100}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <rect width={cols * 100} height={rows * 100} fill={PAPER} />
      {tiles.map((t) => <svg key={t.i} x={(t.i % cols) * 100} y={Math.floor(t.i / cols) * 100} width="100" height="100" viewBox="0 0 100 100" className={t.rank < count ? 'tile in' : 'tile'}>
        <g transform={`rotate(${t.turn} 50 50)`}>{t.body}</g></svg>)}
    </svg>
  )
})

/** Крупные фигуры 400×400 для фона. */
const FIGURES: ((r: () => number) => ReactNode)[] = [
  () => range(13).map((i) => <circle key={i} cx={200 + i * 3} cy={200} r={14 + i * 14} fill="none" stroke={INK} strokeWidth={1 + i * .35} />),
  (r) => { // растровый диск
    const dx = r() * 2 - 1
    return range(20 * 20).map((i) => {
      const x = 10 + (i % 20) * 20, y = 10 + Math.floor(i / 20) * 20
      return Math.hypot(x - 200, y - 200) > 192 ? null : <circle key={i} cx={x} cy={y} r={Math.max(.8, 5 + ((x - 200) * dx + (y - 200)) / 48)} fill={INK} />
    })
  },
  (r) => { // волны
    const a = 14 + r() * 22, p = r() * 6
    return range(22).map((i) => <path key={i} fill="none" stroke={INK} strokeWidth={i % 4 === 0 ? 4 : 1.5}
      d={'M' + range(41).map((k) => `${k * 10} ${(40 + i * 15 + Math.sin(k / 5 + p) * a * Math.sin(i / 7)).toFixed(1)}`).join('L')} />)
  },
  (r) => { // изолинии
    const ph = range(4).map(() => r() * 6.3)
    return range(14).map((i) => <path key={i} fill="none" stroke={INK} strokeWidth="1.6" d={'M' + range(73).map((k) => {
      const t = (k / 72) * Math.PI * 2, R = 14 + i * 12 + i * (Math.sin(2 * t + ph[0]) * 1.6 + Math.sin(3 * t + ph[1]) * 1.4 + Math.cos(5 * t + ph[2]) * .5)
      return `${(200 + Math.cos(t) * R).toFixed(1)} ${(200 + Math.sin(t) * R).toFixed(1)}`
    }).join('L')} />)
  },
  () => <><path d="M200 10A190 190 0 0 1 200 390Z" fill={INK} />{range(10).map((i) => <path key={i} d={`M190 ${28 + i * 38}H${190 - Math.sqrt(Math.max(0, 190 ** 2 - (28 + i * 38 - 200) ** 2))}`} stroke={INK} strokeWidth="6" />)}</>,
  () => range(48).map((i) => <path key={i} d="M200 200L400 200" stroke={INK} strokeWidth={i % 4 ? 1.5 : 7} strokeDasharray={i % 2 ? '60 12' : undefined} strokeDashoffset={i * 5} transform={`rotate(${i * 7.5} 200 200)`} />),
  (r) => { const n = 5 + Math.floor(r() * 4); return range(16).map((i) => <polygon key={i} fill="none" stroke={INK} strokeWidth="2" transform={`rotate(${i * 5} 200 200)`}
    points={range(n).map((k) => `${200 + Math.cos(k / n * 6.283) * (190 - i * 11)},${200 + Math.sin(k / n * 6.283) * (190 - i * 11)}`).join(' ')} />) },
  () => range(7).map((i) => <g key={i} transform={`translate(${i * 24} ${i * 24})`}><rect x="20" y="20" width="200" height="200" fill={i % 2 ? INK : PAPER} stroke={INK} strokeWidth="2" /></g>),
  () => <path fill="none" stroke={INK} strokeWidth="9" d={'M' + range(260).map((k) => { const t = k / 12, R = 4 + k * .72; return `${(200 + Math.cos(t) * R).toFixed(1)} ${(200 + Math.sin(t) * R).toFixed(1)}` }).join('L')} />,
]
const SPOTS = [ // [left%, top px, размер]
  [-9, 130, 360], [87, 90, 380], [-11, 640, 460], [71, 640, 420], [26, 1010, 420], [86, 1090, 360],
] as const

/** Фон: новые фигуры при каждом заходе. */
export const Backdrop = memo(function Backdrop() {
  const figures = useMemo(() => {
    const r = rng(String(Math.random()))
    const order = range(FIGURES.length).sort(() => r() - .5)
    return SPOTS.map(([left, top, size], i) => ({ left: left + r() * 4 - 2, top: top + r() * 70 - 35, size: size * (.85 + r() * .3), turn: Math.floor(r() * 24) * 15, body: FIGURES[order[i % order.length]](r) }))
  }, [])
  return <div className="backdrop" aria-hidden="true">{figures.map((f, i) => (
    <svg key={i} viewBox="0 0 400 400" style={{ width: f.size, height: f.size, left: `${f.left}%`, top: f.top, transform: `rotate(${f.turn}deg)` }}>{f.body}</svg>
  ))}</div>
})
