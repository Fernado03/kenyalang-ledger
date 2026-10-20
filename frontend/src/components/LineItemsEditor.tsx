import { formatConfidence } from '../lib/format';
import type { DraftLineField, DraftLineItem, ReceiptLineItem } from '../types/receipt';

interface LineItemsEditorProps {
  items: DraftLineItem[];
  serverLineItems: ReceiptLineItem[];
  activeKey: string | null;
  onChange: (key: string, field: DraftLineField, value: string) => void;
  onRemove: (key: string) => void;
  onAdd: () => void;
  onFocusRow: (key: string) => void;
}

const HEADER_CELL = 'px-2 py-1 text-[11px] uppercase tracking-wider text-text-muted';

const INPUT_CLASS =
  'h-9 w-full border border-border bg-surface px-2 text-sm text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

const NUMERIC_INPUT_CLASS = `${INPUT_CLASS} text-right font-mono-numbers`;

const DELETE_BUTTON_CLASS =
  'inline-flex h-11 w-11 items-center justify-center border border-border bg-surface text-sm text-text-primary transition-colors duration-100 ease-out hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

const ADD_BUTTON_CLASS =
  'inline-flex h-11 items-center border border-border bg-surface px-3 text-sm font-medium text-text-primary transition-colors duration-100 ease-out hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

/** Low-confidence OCR threshold: amber row + dashed underline + ? badge. */
const LOW_CONFIDENCE = 0.8;

function LineRow({
  item,
  index,
  serverItem,
  active,
  onChange,
  onRemove,
  onFocusRow,
}: {
  item: DraftLineItem;
  index: number;
  serverItem: ReceiptLineItem | undefined;
  active: boolean;
  onChange: (key: string, field: DraftLineField, value: string) => void;
  onRemove: (key: string) => void;
  onFocusRow: (key: string) => void;
}): JSX.Element {
  const lowConfidence = serverItem !== undefined && serverItem.confidence < LOW_CONFIDENCE;

  return (
    <tr
      className={`h-dense-row border-b border-border transition-colors duration-100 ease-out ${
        active ? 'bg-brand-50' : lowConfidence ? 'bg-warning-bg' : ''
      }`}
    >
      <td className="px-1 py-1">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={item.description}
            onChange={(event) => onChange(item.key, 'description', event.target.value)}
            onFocus={() => onFocusRow(item.key)}
            aria-label={`Line ${index + 1} description`}
            className={`${INPUT_CLASS} flex-1 ${
              lowConfidence ? 'decoration-warning-border decoration-dashed underline' : ''
            }`}
          />
          {lowConfidence && serverItem !== undefined && (
            <span className="shrink-0 text-xs font-medium text-warning-text">
              <span aria-hidden="true">?</span> {formatConfidence(serverItem.confidence)}
            </span>
          )}
        </div>
      </td>
      <td className="px-1 py-1">
        <input
          type="text"
          inputMode="decimal"
          value={item.quantity}
          onChange={(event) => onChange(item.key, 'quantity', event.target.value)}
          onFocus={() => onFocusRow(item.key)}
          aria-label={`Line ${index + 1} quantity`}
          className={NUMERIC_INPUT_CLASS}
        />
      </td>
      <td className="px-1 py-1">
        <input
          type="text"
          inputMode="decimal"
          value={item.unit_price}
          onChange={(event) => onChange(item.key, 'unit_price', event.target.value)}
          onFocus={() => onFocusRow(item.key)}
          aria-label={`Line ${index + 1} unit price`}
          className={NUMERIC_INPUT_CLASS}
        />
      </td>
      <td className="px-1 py-1">
        <input
          type="text"
          inputMode="decimal"
          value={item.line_total}
          onChange={(event) => onChange(item.key, 'line_total', event.target.value)}
          onFocus={() => onFocusRow(item.key)}
          aria-label={`Line ${index + 1} total`}
          className={NUMERIC_INPUT_CLASS}
        />
      </td>
      <td className="px-1 py-1">
        <button
          type="button"
          aria-label={`Remove line ${index + 1}`}
          className={DELETE_BUTTON_CLASS}
          onClick={() => onRemove(item.key)}
        >
          <span aria-hidden="true">✕</span>
        </button>
      </td>
    </tr>
  );
}

/**
 * SCR-03 §2.2 editable line-item grid. The parent draft is the single source of
 * truth: every keystroke fires `onChange` upward, and rows mirrored against a
 * low-confidence server line render amber with a dashed underline.
 */
export default function LineItemsEditor({
  items,
  serverLineItems,
  activeKey,
  onChange,
  onRemove,
  onAdd,
  onFocusRow,
}: LineItemsEditorProps): JSX.Element {
  return (
    <div className="relative overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full min-w-[32rem]">
        <thead className="border-b border-border bg-surface-subtle/70">
          <tr>
            <th className={HEADER_CELL}>Description</th>
            <th className={HEADER_CELL}>Qty</th>
            <th className={HEADER_CELL}>Unit (RM)</th>
            <th className={HEADER_CELL}>Total (RM)</th>
            <th className="w-11 px-1 py-1" aria-label="Delete line" />
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <LineRow
              key={item.key}
              item={item}
              index={index}
              serverItem={serverLineItems[index]}
              active={activeKey === item.key}
              onChange={onChange}
              onRemove={onRemove}
              onFocusRow={onFocusRow}
            />
          ))}
        </tbody>
      </table>
      <div className="flex items-center justify-between border-t border-border px-2 py-1">
        <button type="button" className={ADD_BUTTON_CLASS} onClick={onAdd}>
          + Add Line (Alt+A)
        </button>
        <span className="font-mono-numbers text-xs text-text-muted">{items.length} lines</span>
      </div>
    </div>
  );
}
