import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, PointerEvent as ReactPointerEvent, SetStateAction } from 'react';

import { receiptImageUrl } from '../api/client';
import { formatConfidence } from '../lib/format';
import { useSessionStore } from '../store/sessionStore';
import type { FieldProvenance, OcrToken, ReceiptLineItem } from '../types/receipt';

/** Zoom bounds and step mirrored by the review page's lifted zoom state. */
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.25;

/** Bounding-box colour encoding (docs/04_ui_specs.md §4.3). */
const ACTIVE_STROKE = '#14B8A6';
const ACTIVE_FILL = 'rgba(20,184,166,0.15)';
const LOW_CONFIDENCE_STROKE = '#F59E0B';
const LOW_CONFIDENCE_FILL = 'rgba(245,158,11,0.10)';
const MISMATCH_STROKE = '#EF4444';
const MISMATCH_FILL = 'rgba(239,68,68,0.10)';
const IDLE_STROKE = 'rgba(100,116,139,0.55)';

/** Confidence below which a provenance box is flagged amber. */
const LOW_CONFIDENCE_THRESHOLD = 0.8;

/** Overlay geometry in viewBox units (normalized coords × 1000). */
const VIEWBOX_SIZE = 1000;

/** One drawn provenance box with its hover/flag state resolved. */
interface OverlayBox {
  id: string;
  name: string;
  confidence: number;
  x: number;
  y: number;
  width: number;
  height: number;
  isActive: boolean;
  isMismatch: boolean;
  token: OcrToken | null;
}

/** Fill/stroke decision for one box: active teal → math-mismatch red → amber. */
function boxStyle(box: OverlayBox): {
  stroke: string;
  fill: string;
  strokeWidth: number;
  dashArray: string | undefined;
} {
  if (box.isActive) {
    return { stroke: ACTIVE_STROKE, fill: ACTIVE_FILL, strokeWidth: 2, dashArray: undefined };
  }
  if (box.isMismatch) {
    return { stroke: MISMATCH_STROKE, fill: MISMATCH_FILL, strokeWidth: 2, dashArray: undefined };
  }
  if (box.confidence < LOW_CONFIDENCE_THRESHOLD) {
    return {
      stroke: LOW_CONFIDENCE_STROKE,
      fill: LOW_CONFIDENCE_FILL,
      strokeWidth: 1,
      dashArray: '4',
    };
  }
  return { stroke: IDLE_STROKE, fill: 'transparent', strokeWidth: 1, dashArray: undefined };
}

/** Normalizes a `[x_min, y_min, x_max, y_max]` bbox into viewBox pixels. */
function toPixels(bbox: number[]): { x: number; y: number; width: number; height: number } | null {
  if (bbox.length < 4) {
    return null;
  }
  const [x0, y0, x1, y1] = bbox;
  if (![x0, y0, x1, y1].every((value) => Number.isFinite(value))) {
    return null;
  }
  const width = Math.abs(x1 - x0) * VIEWBOX_SIZE;
  const height = Math.abs(y1 - y0) * VIEWBOX_SIZE;
  if (width <= 0 || height <= 0) {
    return null;
  }
  return {
    x: Math.min(x0, x1) * VIEWBOX_SIZE,
    y: Math.min(y0, y1) * VIEWBOX_SIZE,
    width,
    height,
  };
}

/** Intersection-over-union score between two normalized bboxes. */
function overlapScore(a: number[], b: number[]): number {
  const ix0 = Math.max(Math.min(a[0], a[2]), Math.min(b[0], b[2]));
  const iy0 = Math.max(Math.min(a[1], a[3]), Math.min(b[1], b[3]));
  const ix1 = Math.min(Math.max(a[0], a[2]), Math.max(b[0], b[2]));
  const iy1 = Math.min(Math.max(a[1], a[3]), Math.max(b[1], b[3]));
  const width = ix1 - ix0;
  const height = iy1 - iy0;
  if (width <= 0 || height <= 0) {
    return 0;
  }
  const intersection = width * height;
  const areaA = Math.abs(a[2] - a[0]) * Math.abs(a[3] - a[1]);
  const areaB = Math.abs(b[2] - b[0]) * Math.abs(b[3] - b[1]);
  const union = areaA + areaB - intersection;
  return union > 0 ? intersection / union : 0;
}

/** OCR token covering a bbox, used for the hover tooltip text. */
function matchToken(bbox: number[], tokens: OcrToken[]): OcrToken | null {
  let best: OcrToken | null = null;
  let bestScore = 0.25;
  for (const token of tokens) {
    if (token.bbox === null || token.bbox.length < 4) {
      continue;
    }
    const score = overlapScore(bbox, token.bbox);
    if (score > bestScore) {
      bestScore = score;
      best = token;
    }
  }
  return best;
}

/** A line row is active when the focused key names that row: `line_items[2]`. */
function isActiveLineRow(activeField: string | null, index: number): boolean {
  if (activeField === null) {
    return false;
  }
  return (
    activeField === `line_items[${index}]` || activeField.startsWith(`line_items[${index}].`)
  );
}

const ICON_BUTTON =
  'inline-flex h-11 w-11 items-center justify-center border border-border bg-surface text-sm text-text-primary hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

const TEXT_BUTTON =
  'inline-flex h-11 items-center justify-center border border-border bg-surface px-3 text-sm font-medium text-text-primary hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

/**
 * Props for the SCR-03 receipt viewport. Zoom lives in the review page so the
 * `[`/`]`/`R` bindings and the on-screen buttons stay in one place.
 */
interface ReceiptCanvasProps {
  clientId: string;
  receiptId: string;
  fields: FieldProvenance[];
  lineItems: ReceiptLineItem[];
  tokens: OcrToken[];
  activeField: string | null;
  onHoverToken: (token: OcrToken | null) => void;
  mismatchFields: string[];
  processingError: string | null;
  scale: number;
  setScale: Dispatch<SetStateAction<number>>;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

/**
 * Receipt image viewport: authenticated blob fetch, GPU-only pan/zoom, and the
 * provenance bounding-box layer (docs/04_ui_specs.md §4.3). `[`/`]`/`R` are
 * wired by the review page through the lifted zoom props, so no second key
 * listener is attached here.
 */
export default function ReceiptCanvas({
  clientId,
  receiptId,
  fields,
  lineItems,
  tokens,
  activeField,
  onHoverToken,
  mismatchFields,
  processingError,
  scale,
  setScale,
  onZoomIn,
  onZoomOut,
  onReset,
}: ReceiptCanvasProps): JSX.Element {
  const accountantId = useSessionStore((state) => state.accountantId);
  const panRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState<{ x: number; y: number; text: string } | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  // Authenticated blob fetch; the object URL is revoked on cleanup.
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    const headers: HeadersInit =
      accountantId === null ? {} : { 'X-Accountant-Id': accountantId };

    fetch(receiptImageUrl(clientId, receiptId), { headers })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Image request failed (HTTP ${response.status})`);
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setImageUrl(objectUrl);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setImageError(error instanceof Error ? error.message : 'Image unavailable');
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [accountantId, clientId, receiptId]);

  const clampScale = useCallback(
    (value: number): number => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value)),
    [],
  );

  // Native non-passive wheel listener: plain or ctrl+wheel zooms toward the cursor.
  useEffect(() => {
    const node = panRef.current;
    if (node === null) {
      return undefined;
    }
    const handleWheel = (event: WheelEvent): void => {
      event.preventDefault();
      const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      const nextScale = clampScale(scale * factor);
      const ratio = nextScale / scale;
      const rect = node.getBoundingClientRect();
      const cursorX = event.clientX - rect.left;
      const cursorY = event.clientY - rect.top;
      setTx((prev) => cursorX - (cursorX - prev) * ratio);
      setTy((prev) => cursorY - (cursorY - prev) * ratio);
      setScale(nextScale);
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      node.removeEventListener('wheel', handleWheel);
    };
  }, [clampScale, scale, setScale]);

  const boxes = useMemo<OverlayBox[]>(() => {
    const result: OverlayBox[] = [];
    for (const field of fields) {
      if (field.bbox === null) {
        continue;
      }
      const geometry = toPixels(field.bbox);
      if (geometry === null) {
        continue;
      }
      result.push({
        id: `field:${field.name}`,
        name: field.name,
        confidence: field.confidence,
        ...geometry,
        isActive: activeField === field.name,
        isMismatch: mismatchFields.includes(field.name),
        token: matchToken(field.bbox, tokens),
      });
    }
    lineItems.forEach((item, index) => {
      if (item.bbox === null) {
        return;
      }
      const geometry = toPixels(item.bbox);
      if (geometry === null) {
        return;
      }
      result.push({
        id: `line:${item.id}:${index}`,
        name: item.description === '' ? `Line ${index + 1}` : item.description,
        confidence: item.confidence,
        ...geometry,
        isActive: isActiveLineRow(activeField, index),
        isMismatch: mismatchFields.some((name) => name.startsWith(`line_items[${index}]`)),
        token: matchToken(item.bbox, tokens),
      });
    });
    return result;
  }, [activeField, fields, lineItems, mismatchFields, tokens]);

  const showTooltip = useCallback(
    (event: ReactPointerEvent<SVGRectElement>, box: OverlayBox): void => {
      const node = panRef.current;
      if (node === null) {
        return;
      }
      const rect = node.getBoundingClientRect();
      const text = `${box.token?.text ?? box.name} (Conf: ${formatConfidence(
        box.token?.confidence ?? box.confidence,
      )})`;
      setHovered({ x: event.clientX - rect.left + 12, y: event.clientY - rect.top + 12, text });
      onHoverToken(box.token);
    },
    [onHoverToken],
  );

  const hideTooltip = useCallback((): void => {
    setHovered(null);
    onHoverToken(null);
  }, [onHoverToken]);

  const handleReset = useCallback((): void => {
    setTx(0);
    setTy(0);
    onReset();
  }, [onReset]);

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>): void => {
      if (event.button !== 0) {
        return;
      }
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: tx,
        originY: ty,
      };
      setDragging(true);
    },
    [tx, ty],
  );

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>): void => {
    const drag = dragRef.current;
    if (drag === null) {
      return;
    }
    setTx(drag.originX + (event.clientX - drag.startX));
    setTy(drag.originY + (event.clientY - drag.startY));
  }, []);

  const handlePointerUp = useCallback((): void => {
    dragRef.current = null;
    setDragging(false);
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-subtle">
      <div className="flex h-dense-row shrink-0 items-center gap-2 border-b border-border bg-surface px-2">
        <button type="button" className={ICON_BUTTON} onClick={onZoomOut} aria-label="Zoom out">
          −
        </button>
        <span className="w-14 text-center font-mono-numbers text-xs text-text-secondary">
          {Math.round(scale * 100)}%
        </span>
        <button type="button" className={ICON_BUTTON} onClick={onZoomIn} aria-label="Zoom in">
          +
        </button>
        <button
          type="button"
          className={TEXT_BUTTON}
          onClick={handleReset}
          aria-label="Reset zoom and center"
        >
          Reset
        </button>
      </div>

      <div
        ref={panRef}
        className={`relative min-h-0 flex-1 overflow-hidden ${
          dragging ? 'cursor-grabbing' : 'cursor-grab'
        }`}
        style={{ touchAction: 'none' }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {imageError === null ? (
          <div
            className="relative"
            style={{
              transform: `translate3d(${tx}px, ${ty}px, 0) scale(${scale})`,
              transformOrigin: '0 0',
              willChange: 'transform',
              transition: 'none',
            }}
          >
            {imageUrl === null ? (
              <div className="h-64 w-full animate-pulse bg-surface-subtle" />
            ) : (
              <ReceiptImage src={imageUrl} alt={`Receipt ${receiptId}`} />
            )}
            <svg
              className="pointer-events-none absolute inset-0"
              viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {boxes.map((box) => {
                const style = boxStyle(box);
                return (
                  <rect
                    key={box.id}
                    x={box.x}
                    y={box.y}
                    width={box.width}
                    height={box.height}
                    fill={style.fill}
                    stroke={style.stroke}
                    strokeWidth={style.strokeWidth}
                    strokeDasharray={style.dashArray}
                    pointerEvents="auto"
                    onPointerEnter={(event) => showTooltip(event, box)}
                    onPointerMove={(event) => showTooltip(event, box)}
                    onPointerLeave={hideTooltip}
                  />
                );
              })}
            </svg>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-4">
            <div className="border border-border bg-surface p-4">
              <p className="text-sm font-semibold text-text-primary">Image unavailable</p>
              <p className="mt-1 text-xs text-text-secondary">{imageError}</p>
              {processingError !== null && processingError !== undefined && processingError !== '' && (
                <p className="mt-1 font-mono-numbers text-xs text-mismatch-text">
                  {processingError}
                </p>
              )}
            </div>
          </div>
        )}

        {hovered !== null && (
          <div
            className="pointer-events-none absolute z-10 bg-border-focus px-2 py-1 text-xs text-surface"
            style={{ left: hovered.x, top: hovered.y }}
          >
            {hovered.text}
          </div>
        )}
      </div>
    </div>
  );
}

/** The image node itself: memoized so pan/zoom never re-render it. */
const ReceiptImage = memo(function ReceiptImage({
  src,
  alt,
}: {
  src: string;
  alt: string;
}): JSX.Element {
  return <img src={src} alt={alt} draggable={false} className="block h-auto w-full select-none" />;
});
