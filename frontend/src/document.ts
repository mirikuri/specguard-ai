/** Разбор исходного текста для показа. Смещения — в символах Unicode, как в Python; служебные знаки Markdown не показываются. */
export interface Piece { start: number; end: number; bold?: boolean; code?: boolean }
export interface Row { head: boolean; cells: Piece[][] }
export type Block =
  | { kind: 'heading'; level: number; pieces: Piece[] }
  | { kind: 'item'; depth: number; marker: string; pieces: Piece[] }
  | { kind: 'para' | 'code'; pieces: Piece[] }
  | { kind: 'table'; rows: Row[] }

type Line = { start: number; end: number; text: string[] }

function inline(chars: string[], start: number, end: number, pdf: boolean): Piece[] {
  if (pdf) return end > start ? [{ start, end }] : []
  const out: Piece[] = []
  let bold = false, from = start, i = start
  const flush = (to: number) => { if (to > from) out.push(bold ? { start: from, end: to, bold } : { start: from, end: to }) }
  const find = (mark: string, at: number) => {
    for (let k = at; k + mark.length <= end; k++) if (chars.slice(k, k + mark.length).join('') === mark) return k
    return -1
  }
  while (i < end) {
    if (chars[i] === '\\' && i + 1 < end && /[\\`*_{}[\]()#+\-.!|<>~]/.test(chars[i + 1])) {
      flush(i); from = i + 1; i += 2
    } else if (chars[i] === '`') {
      const close = find('`', i + 1)
      if (close > i + 1) {
        flush(i); out.push({ start: i + 1, end: close, code: true, ...(bold && { bold }) }); i = from = close + 1
      } else i++
    } else if (chars[i] === '*' && chars[i + 1] === '*' && i + 1 < end) {
      const opens = !bold && i + 2 < end && !/\s/.test(chars[i + 2]) && find('**', i + 3) > 0
      if (bold || opens) { flush(i); bold = !bold; i += 2; from = i } else i += 2
    } else i++
  }
  flush(end)
  return out
}

function trim(chars: string[], start: number, end: number): [number, number] {
  while (start < end && /\s/.test(chars[start])) start++
  while (end > start && /\s/.test(chars[end - 1])) end--
  return [start, end]
}

function cells(chars: string[], line: Line, pdf: boolean): Piece[][] {
  let [a, b] = trim(chars, line.start, line.end)
  if (chars[a] === '|') a++
  if (chars[b - 1] === '|' && chars[b - 2] !== '\\' && b > a) b--
  const out: Piece[][] = []
  let from = a, code = false
  for (let i = a; i <= b; i++) {
    if (i < b && chars[i] === '`') code = !code
    if (i === b || (chars[i] === '|' && chars[i - 1] !== '\\' && !code)) {
      const [s, e] = trim(chars, from, i)
      out.push(inline(chars, s, e, pdf))
      from = i + 1
    }
  }
  return out
}

export function parse(text: string, pdf: boolean): Block[] {
  const chars = Array.from(text)
  const lines: Line[] = []
  for (let i = 0, s = 0; i <= chars.length; i++)
    if (i === chars.length || chars[i] === '\n') { lines.push({ start: s, end: i, text: chars.slice(s, i) }); s = i + 1 }
  const out: Block[] = []
  let para: Line[] = [], item: { block: Extract<Block, { kind: 'item' }>; lines: [number, number][] } | null = null
  const str = (l: Line) => l.text.join('')
  const close = () => {
    if (para.length) {
      const [s, e] = trim(chars, para[0].start, para[para.length - 1].end)
      out.push({ kind: 'para', pieces: inline(chars, s, e, pdf) })
    }
    para = []
    item = null
  }
  for (let n = 0; n < lines.length; n++) {
    const l = lines[n], s = str(l)
    if (!s.trim()) { close(); continue }
    let m: RegExpMatchArray | null
    if ((m = s.match(/^\s*(```|~~~)/))) {
      close()
      let k = n + 1
      while (k < lines.length && !str(lines[k]).trim().startsWith(m[1])) k++
      if (k > n + 1) out.push({ kind: 'code', pieces: [{ start: lines[n + 1].start, end: lines[k - 1].end }].filter((p) => p.end > p.start) })
      n = k
    } else if ((m = s.match(/^\s{0,3}(#{1,6})\s+/))) {
      close()
      const [a, b] = trim(chars, l.start + Array.from(m[0]).length, l.end)
      out.push({ kind: 'heading', level: m[1].length, pieces: inline(chars, a, b, pdf) })
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(s)) {
      close()
    } else if (s.trim().startsWith('|')) {
      close()
      const rows: Row[] = []
      let k = n
      for (; k < lines.length && str(lines[k]).trim().startsWith('|'); k++) {
        if (/^[\s|:\-]+$/.test(str(lines[k])) && str(lines[k]).includes('-')) { if (rows.length) rows[rows.length - 1].head = true }
        else rows.push({ head: false, cells: cells(chars, lines[k], pdf) })
      }
      out.push({ kind: 'table', rows })
      n = k - 1
    } else if ((m = s.match(/^(\s*)([-*+]|\d+[.)])\s+/))) {
      close()
      const [a, b] = trim(chars, l.start + Array.from(m[0]).length, l.end)
      const block = { kind: 'item' as const, depth: Math.floor(m[1].length / 2), marker: /\d/.test(m[2]) ? m[2] : '–', pieces: inline(chars, a, b, pdf) }
      out.push(block)
      item = { block, lines: [[a, b]] }
    } else if ((m = s.match(/^\s*>\s?/)) && !para.length) {
      close()
      const [a, b] = trim(chars, l.start + m[0].length, l.end)
      if (b > a) out.push({ kind: 'para', pieces: inline(chars, a, b, pdf) })
    } else if (item) { // продолжение пункта списка
      const cur: { block: Extract<Block, { kind: 'item' }>; lines: [number, number][] } = item
      const [, b] = trim(chars, l.start, l.end)
      cur.lines[0][1] = b
      cur.block.pieces = inline(chars, cur.lines[0][0], b, pdf)
    } else para.push(l)
  }
  close()
  return out.filter((b) => (b.kind === 'table' ? b.rows.length : b.pieces.length))
}
