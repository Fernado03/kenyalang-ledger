import { describe, expect, it } from 'vitest';
import { resolveReviewShortcut } from './reviewShortcuts';

describe('resolveReviewShortcut', () => {
  const typing = { typing: true, focusedLine: 'line-1' };
  const idle = { typing: false, focusedLine: 'line-1' };

  it('Escape while typing only blurs the field', () => {
    expect(
      resolveReviewShortcut(
        { key: 'Escape', metaKey: false, ctrlKey: false, altKey: false },
        typing,
      ),
    ).toBe('blur');
  });

  it('Escape outside a field asks to reject', () => {
    expect(
      resolveReviewShortcut(
        { key: 'Escape', metaKey: false, ctrlKey: false, altKey: false },
        idle,
      ),
    ).toBe('reject');
  });

  it('Cmd/Ctrl+Enter is ignored while typing', () => {
    expect(
      resolveReviewShortcut(
        { key: 'Enter', metaKey: true, ctrlKey: false, altKey: false },
        typing,
      ),
    ).toBeNull();
    expect(
      resolveReviewShortcut(
        { key: 'Enter', metaKey: false, ctrlKey: true, altKey: false },
        typing,
      ),
    ).toBeNull();
  });

  it('Cmd/Ctrl+Enter saves outside a field', () => {
    expect(
      resolveReviewShortcut(
        { key: 'Enter', metaKey: true, ctrlKey: false, altKey: false },
        idle,
      ),
    ).toBe('save');
    expect(
      resolveReviewShortcut(
        { key: 'Enter', metaKey: false, ctrlKey: true, altKey: false },
        idle,
      ),
    ).toBe('save');
  });

  it('Alt+A adds a line only outside a field', () => {
    expect(
      resolveReviewShortcut({ key: 'a', metaKey: false, ctrlKey: false, altKey: true }, idle),
    ).toBe('add-line');
    expect(
      resolveReviewShortcut({ key: 'A', metaKey: false, ctrlKey: false, altKey: true }, typing),
    ).toBeNull();
  });

  it('Alt+Backspace deletes only the focused line and only outside a field', () => {
    expect(
      resolveReviewShortcut(
        { key: 'Backspace', metaKey: false, ctrlKey: false, altKey: true },
        idle,
      ),
    ).toBe('delete-line');
    expect(
      resolveReviewShortcut(
        { key: 'Backspace', metaKey: false, ctrlKey: false, altKey: true },
        { typing: false, focusedLine: null },
      ),
    ).toBeNull();
    expect(
      resolveReviewShortcut(
        { key: 'Backspace', metaKey: false, ctrlKey: false, altKey: true },
        typing,
      ),
    ).toBeNull();
  });

  it('leaves unbound and modifier-less keys alone', () => {
    expect(
      resolveReviewShortcut({ key: 'Enter', metaKey: false, ctrlKey: false, altKey: false }, idle),
    ).toBeNull();
    expect(
      resolveReviewShortcut({ key: 'a', metaKey: false, ctrlKey: false, altKey: false }, idle),
    ).toBeNull();
    expect(
      resolveReviewShortcut({ key: 'Escape', metaKey: true, ctrlKey: false, altKey: true }, idle),
    ).toBe('reject');
  });
});
