import type { ReactNode } from 'react'

interface PageHeaderProps {
  eyebrow: string
  title: string
  meta?: ReactNode
  actions?: ReactNode
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
