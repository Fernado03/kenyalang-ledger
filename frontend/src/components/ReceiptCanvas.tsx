import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, PointerEvent as ReactPointerEvent, SetStateAction } from 'react';

import { receiptImageUrl } from '../api/client';
import { formatConfidence } from '../lib/format';
import { Icon } from './Icon';
import { useSessionStore } from '../store/sessionStore';
import type { FieldProvenance, OcrToken, ReceiptLineItem } from '../types/receipt';

/** Zoom bounds and step mirrored by the review page's lifted zoom state. */
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.25;

/** Bounding-box colour encoding (docs/04_ui_specs.md §4.3). */
const ACTIVE_STROKE = '#147A6C';
const ACTIVE_FILL = 'rgba(20,122,108,0.14)';
const LOW_CONFIDENCE_STROKE = '#B07A1E';
const LOW_CONFIDENCE_FILL = 'rgba(176,122,30,0.10)';
const MISMATCH_STROKE = '#B4452F';
const MISMATCH_FILL = 'rgba(180,69,47,0.10)';
const IDLE_STROKE = 'rgba(23,26,24,0.45)';

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
  'inline-flex h-11 w-11 items-center justify-center border border-charcoal-rule bg-transparent text-text-inverse transition-colors duration-100 ease-out hover:bg-charcoal-rule';

const TEXT_BUTTON =
  'inline-flex h-11 items-center justify-center gap-1.5 border border-charcoal-rule bg-transparent px-3 text-ui font-medium text-text-inverse transition-colors duration-100 ease-out hover:bg-charcoal-rule';

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
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [stage, setStage] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  // Track the stage box so the scan can be contained inside it at 100%.
  useEffect(() => {
    const node = panRef.current;
    if (node === null) {
      return undefined;
    }
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box !== undefined) {
        setStage({ w: box.width, h: box.height });
      }
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  const handleNaturalSize = useCallback((w: number, h: number): void => {
    setNatural({ w, h });
  }, []);

  // Contain-fit at 100%: both axes are respected so a landscape scan on a tall
  // pane is centred rather than stranded at the top of an empty stage.
  const fit = useMemo(() => {
    if (natural === null || stage.w === 0 || stage.h === 0) {
      return null;
    }
    const factor = Math.min(stage.w / natural.w, stage.h / natural.h);
    return {
      width: Math.round(natural.w * factor),
      height: Math.round(natural.h * factor),
    };
  }, [natural, stage]);

  // Top-left of the fitted scan inside the stage. Zoom scales from this corner,
  // so the resting position must be part of the transform rather than layout.
  const originX = fit === null ? 0 : Math.round((stage.w - fit.width) / 2);
  const originY = fit === null ? 0 : Math.round((stage.h - fit.height) / 2);

  // Authenticated blob fetch; the object URL is revoked on cleanup.
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    const controller = new AbortController();
    const headers: HeadersInit =
      accountantId === null ? {} : { 'X-Accountant-Id': accountantId };

    fetch(receiptImageUrl(clientId, receiptId), { headers, signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Image request failed (HTTP ${response.status})`);
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          objectUrl = null;
          return;
        }
        setImageUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setImageError(error instanceof Error ? error.message : 'Image unavailable');
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
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
      setTx((prev) => {
        const base = originX + prev;
        return cursorX - (cursorX - base) * ratio - originX;
      });
      setTy((prev) => {
        const base = originY + prev;
        return cursorY - (cursorY - base) * ratio - originY;
      });
      setScale(nextScale);
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      node.removeEventListener('wheel', handleWheel);
    };
  }, [clampScale, originX, originY, scale, setScale]);

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
    <div className="on-dark flex h-full min-h-0 flex-col bg-charcoal">
      <div className="flex h-dense-row shrink-0 items-center gap-2 border-b border-charcoal-rule bg-charcoal-raised px-2">
        <button type="button" className={ICON_BUTTON} onClick={onZoomOut} aria-label="Zoom out">
          <Icon name="minus" size={16} />
        </button>
        <span className="w-14 text-center font-mono-numbers text-label text-text-inverse">
          {Math.round(scale * 100)}%
        </span>
        <button type="button" className={ICON_BUTTON} onClick={onZoomIn} aria-label="Zoom in">
          <Icon name="plus" size={16} />
        </button>
        <button
          type="button"
          className={TEXT_BUTTON}
          onClick={handleReset}
          aria-label="Reset zoom and center"
        >
          <Icon name="reset" size={16} /> Reset
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
            className="relative shrink-0"
            style={{
              // Fit the whole scan inside the stage at 100%: cap both axes so a
              // landscape photo on a portrait pane is contained, not cropped or
              // marooned at the top of a tall empty stage. The centring offset is
              // folded into the transform (not flex) so cursor-anchored zoom keeps
              // pointing at the same pixel of the scan.
              width: fit === null ? undefined : `${fit.width}px`,
              height: fit === null ? undefined : `${fit.height}px`,
              transform: `translate3d(${originX + tx}px, ${originY + ty}px, 0) scale(${scale})`,
              transformOrigin: '0 0',
              transition: 'none',
            }}
          >
            {imageUrl === null ? (
              <div className="h-64 w-[min(100%,28rem)] animate-pulse bg-charcoal-raised" />
            ) : (
              <ReceiptImage
                src={imageUrl}
                alt="Scanned receipt for review"
                onNaturalSize={handleNaturalSize}
              />
            )}
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
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
            className="pointer-events-none absolute z-10 border border-border bg-surface px-2 py-1 font-mono text-micro text-text-primary shadow-[0_1px_3px_rgba(23,26,24,0.28)]"
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
  onNaturalSize,
}: {
  src: string;
  alt: string;
  onNaturalSize: (w: number, h: number) => void;
}): JSX.Element {
  return (
    <img
      src={src}
      alt={alt}
      draggable={false}
      onLoad={(event) => {
        const node = event.currentTarget;
        if (node.naturalWidth > 0 && node.naturalHeight > 0) {
          onNaturalSize(node.naturalWidth, node.naturalHeight);
        }
      }}
      className="block h-full w-full select-none bg-surface object-contain shadow-[0_1px_3px_rgba(23,26,24,0.28)]"
    />
  );
});
