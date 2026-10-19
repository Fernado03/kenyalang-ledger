/**
 * Keyboard workflow for SCR-03 (docs/04_ui_specs.md §4.4): pure resolution of
 * one keydown into an action, so the page only maps actions onto handlers.
 */

export type ReviewShortcut = 'blur' | 'save' | 'reject' | 'add-line' | 'delete-line';

export interface ReviewShortcutContext {
  /** True while a text field, select, or contenteditable has focus. */
  typing: boolean;
  /** Key of the line row the accountant is working in, if any. */
  focusedLine: string | null;
}

interface ReviewKeyEvent {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
}

/**
 * Escape blurs a focused field and otherwise asks to reject (the page confirms
 * first). ⌘/Ctrl+Enter saves, Alt+A adds a line, Alt+Backspace deletes the
 * focused line — none of those fire while the accountant is typing.
 */
export function resolveReviewShortcut(
  event: ReviewKeyEvent,
  context: ReviewShortcutContext,
): ReviewShortcut | null {
  if (event.key === 'Escape') {
    return context.typing ? 'blur' : 'reject';
  }
  if (context.typing) {
    return null;
  }
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    return 'save';
  }
  if (event.altKey && (event.key === 'a' || event.key === 'A')) {
    return 'add-line';
  }
  if (event.altKey && event.key === 'Backspace' && context.focusedLine !== null) {
    return 'delete-line';
  }
  return null;
}
