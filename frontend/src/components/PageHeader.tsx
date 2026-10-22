import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'

interface PageHeaderProps {
  eyebrow: string
  title: string
  meta?: ReactNode
  actions?: ReactNode
}

interface PageMetaProps {
  /** Workspace or account name. Rendered in `text-primary`. */
  name?: string
  /** Muted secondary detail, rendered at `text-label`. */
  note?: ReactNode
  /** Optional route back into the parent surface. */
  back?: { to: string; label: string }
}

/**
 * The one masthead meta row: name · note · back link. Every page used to roll
 * its own, which drifted into three name colours, two alignments and a
 * separator that appeared on some pages but not others.
 */
export function PageMeta({ name, note, back }: PageMetaProps) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {name !== undefined ? <span className="text-text-primary">{name}</span> : null}
      {name !== undefined && note !== undefined ? (
        <span aria-hidden="true" className="text-text-muted">
          ·
        </span>
      ) : null}
      {note !== undefined ? <span className="text-label text-text-muted">{note}</span> : null}
      {back !== undefined ? (
        <Link to={back.to} className="link-quiet text-label">
          <Icon name="arrow-left" size={14} />
          {back.label}
        </Link>
      ) : null}
    </span>
  )
}

/** Ruled masthead shared by every console page. No page title sits in a card. */
export default function PageHeader({ eyebrow, title, meta, actions }: PageHeaderProps) {
  return (
    <header className="border-b border-border pb-6 lg:pb-7">
      <div className="grid gap-5 lg:grid-cols-12 lg:items-end">
        <div className="min-w-0 lg:col-span-7">
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="mt-2 font-serif text-display font-normal tracking-[-0.015em] text-text-primary">
            {title}
          </h1>
          {meta !== undefined ? (
            <div className="mt-2 max-w-2xl text-body text-text-secondary">{meta}</div>
          ) : null}
        </div>
        {actions !== undefined ? (
          <div className="flex flex-wrap items-center gap-2 lg:col-span-5 lg:justify-end">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  )
}
