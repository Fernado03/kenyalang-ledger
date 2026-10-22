import { describe, expect, it } from 'vitest'
import { parseDetail } from './client'

/**
 * `parseDetail` is the only thing standing between FastAPI's validator objects
 * and the accountant's screen, so it pins the shapes that actually occur.
 */
describe('parseDetail', () => {
  it('returns a string detail verbatim', () => {
    expect(parseDetail({ detail: 'Receipt has already been exported' })).toBe(
      'Receipt has already been exported',
    )
  })

  it('names body fields from a 422 array instead of leaking validator internals', () => {
    const detail = parseDetail({
      detail: [
        {
          type: 'uuid_parsing',
          loc: ['body', 'grand_total'],
          msg: 'Input should be a valid UUID',
          ctx: { error: 'invalid character' },
        },
      ],
    })
    expect(detail).toBe('Check these fields: grand_total.')
    expect(detail).not.toContain('uuid_parsing')
    expect(detail).not.toContain('ctx')
  })

  it('drops path and query parameters, which the accountant cannot fix', () => {
    expect(parseDetail({ detail: [{ type: 'uuid_parsing', loc: ['path', 'receipt_id'] }] })).toBe(
      'The request was rejected. Check the values and try again.',
    )
  })

  it('deduplicates repeated fields and joins the rest', () => {
    expect(
      parseDetail({
        detail: [
          { loc: ['body', 'tax_amount'] },
          { loc: ['body', 'tax_amount'] },
          { loc: ['body', 'line_items', 0, 'quantity'] },
        ],
      }),
    ).toBe('Check these fields: tax_amount, line_items.0.quantity.')
  })

  it('falls back to JSON for an unexpected detail object', () => {
    expect(parseDetail({ detail: { reason: 'nope' } })).toBe('{"reason":"nope"}')
  })

  it('returns empty for a payload with no detail', () => {
    expect(parseDetail({})).toBe('')
    expect(parseDetail(null)).toBe('')
  })
})