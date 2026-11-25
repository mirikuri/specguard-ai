import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { parse, type Block } from '../src/document.ts'

const all = (b: Block) => b.kind === 'table' ? b.rows.flatMap((r) => r.cells.flat()) : b.pieces
const shown = (text: string, pdf = false) => {
  const c = Array.from(text)
  return parse(text, pdf).map((b) => [b.kind, all(b).map((p) => c.slice(p.start, p.end).join('')).join('')])
}

/** Скрыты только служебные знаки; порядок и смещения фрагментов сохранены. */
function lossless(text: string, pdf = false) {
  const c = Array.from(text)
  let at = 0
  for (const p of parse(text, pdf).flatMap(all)) {
    assert.ok(p.start >= at && p.end > p.start, `порядок ${p.start}`)
    const hidden = c.slice(at, p.start).join('')
    assert.match(hidden, /^(?:[\s#*`|:>\\\-+]|\d+[.)]|(?<=`)[\w-]+|~)*$/, JSON.stringify(hidden))
    at = p.end
  }
  assert.match(c.slice(at).join(''), /^[\s#*`|:>\\\-+~]*$/)
}

test('виды блоков и скрытые знаки', () => {
  assert.deepEqual(shown('# Заголовок\n\nТекст **важный** и `код`\nвторая строка\n\n* **Ф-1.** Пункт\n2. Шаг\n'),
    [['heading', 'Заголовок'], ['para', 'Текст важный и код\nвторая строка'], ['item', 'Ф-1. Пункт'], ['item', 'Шаг']])
})
test('таблица и код', () => {
  const t = '| А | Б |\n| :--- | --- |\n| **1** | x\\|y |\n\n```json\n{"a": "**b**"}\n```\n'
  assert.deepEqual(shown(t), [['table', 'АБ1x|y'], ['code', '{"a": "**b**"}']])
  const table = parse(t, false)[0]
  assert.ok(table.kind === 'table' && table.rows.length === 2 && table.rows[0].head && !table.rows[1].head)
})
test('символы вне BMP считаются как в Python', () => {
  const t = '😀 **я**'
  const p = parse(t, false).flatMap(all)
  assert.equal(Array.from(t).slice(p.at(-1)!.start, p.at(-1)!.end).join(''), 'я')
})
test('непарные знаки не съедаются', () => {
  assert.deepEqual(shown('a ** b и 2*3 `x'), [['para', 'a ** b и 2*3 `x']])
})
test('PDF: заголовки и таблицы размечает парсер, знаки внутри строки — текст документа', () => {
  assert.deepEqual(shown('# 1 **a**\n\nb `c`\nd\n\n| x | **y** |\n| --- | --- |', true),
    [['heading', '1 **a**'], ['para', 'b `c`\nd'], ['table', 'x**y**']])
})
test('без потерь', () => {
  for (const f of ['../backend/tests/fixtures/test-requirements.md', '../docs/requirements.md'])
    if (existsSync(f)) lossless(readFileSync(f, 'utf8').replace(/\r\n/g, '\n'))
  lossless('| a |\n| - |\n\n> цитата\n\n---\n\n- [ ] x\n```\nнезакрытый'.replace('- [ ] x\n', ''))
})
