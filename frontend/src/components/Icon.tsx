import type { ReactNode, SVGProps } from 'react'

export type IconName =
  | 'clients'
  | 'inbox'
  | 'dashboard'
  | 'exports'
  | 'camera'
  | 'upload'
  | 'file'
  | 'download'
  | 'plus'
  | 'minus'
  | 'reset'
  | 'close'
  | 'check'
  | 'alert'
  | 'clock'
  | 'chevron-right'
  | 'arrow-left'
  | 'sign-out'

const paths: Record<IconName, ReactNode> = {
  clients: (
    <>
      <path d="M4 20h16M6 20V9l6-4v15M12 20V11h6v9" />
      <path d="M9 9h.01M9 13h.01M9 17h.01M15 14h.01M15 17h.01" />
    </>
  ),
  inbox: (
    <>
      <path d="M4 13h4l2 3h4l2-3h4" />
      <path d="m5 13 2-8h10l2 8v6H5v-6Z" />
    </>
  ),
  dashboard: <path d="M5 19v-8M12 19V5M19 19v-5" />,
  exports: <path d="M5 19h14M14 5h5v5M19 5l-8 8" />,
  camera: (
    <>
      <path d="M4 8h4l1.5-2h5L16 8h4v10H4V8Z" />
      <circle cx="12" cy="13" r="3" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4m-5 5 5-5 5 5" />
      <path d="M5 15v4h14v-4" />
    </>
  ),
  file: (
    <>
      <path d="M7 3h7l4 4v14H7V3Z" />
      <path d="M14 3v4h4" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v11m-5-5 5 5 5-5" />
      <path d="M5 20h14" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  reset: (
    <>
      <path d="M4 10a8 8 0 1 1 1.5 6" />
      <path d="M4 4v6h6" />
    </>
  ),
  close: <path d="m6 6 12 12M18 6 6 18" />,
  check: <path d="m5 12 4 4L19 6" />,
  alert: (
    <>
      <path d="M12 4 3.5 20h17L12 4Z" />
      <path d="M12 9v5M12 17h.01" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </>
  ),
  'chevron-right': <path d="m9 5 7 7-7 7" />,
  'arrow-left': <path d="M19 12H5m6-6-6 6 6 6" />,
  'sign-out': (
    <>
      <path d="M10 5H5v14h5" />
      <path d="M15 8l4 4-4 4M9 12h10" />
    </>
  ),
}

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName
  size?: number
  title?: string
}

// A flex row centres an icon's box on the line box, which includes descender
// space, so `chevron-right` reads ~4px low beside text. Lift its ink onto the
// cap height instead; the offset is proportional so it holds at every size.
const OPTICAL_LIFT: Partial<Record<IconName, string>> = {
  'chevron-right': '-translate-y-[28%]',
}

export function Icon({ name, size = 20, title, className, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      aria-hidden={title === undefined ? true : undefined}
      role={title === undefined ? undefined : 'img'}
      className={[className, OPTICAL_LIFT[name] ?? '']
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      {title !== undefined ? <title>{title}</title> : null}
      {paths[name]}
    </svg>
  )
}

/** Kenyalang's square brand mark. */
// Traced from the generated hornbill artwork; keep geometry in sync with public/favicon-hornbill.svg.
const BRAND_MARK_PATH = `
  M 23.62 35.69 L 23.62 39.91 L 23.78 40.28 L 24.24 40.53 L 51.24 40.53 L 51.53 40.4 L 51.82 39.99 L 51.82 35.61 L 51.57 35.24 L 51.16 35.08 L 24.24 35.08 L 23.83 35.28 Z
  M 9.95 26.36 L 8.63 27.64 L 7.77 28.88 L 6.94 30.86 L 6.65 32.31 L 6.61 55.68 L 6.73 55.92 L 7.11 56.17 L 28.12 56.09 L 28.45 55.55 L 28.41 43.25 L 28.28 43.0 L 27.91 42.75 L 21.43 42.71 L 21.35 27.69 L 20.89 27.36 L 13.17 27.27 L 11.61 26.94 Z
  M 58.96 34.5 L 58.92 31.03 L 58.38 30.2 L 57.14 28.92 L 55.41 27.64 L 53.43 26.61 L 51.36 25.87 L 49.38 25.42 L 47.32 25.17 L 42.53 25.17 L 40.26 26.49 L 39.14 26.9 L 37.7 27.23 L 36.5 27.36 L 24.16 27.36 L 23.74 27.64 L 23.62 27.93 L 23.62 32.23 L 23.78 32.6 L 24.2 32.85 L 53.96 32.85 L 54.0 34.58 L 54.42 35.03 L 58.34 35.08 L 58.67 34.95 Z
  M 46.37 8.32 L 46.08 7.91 L 45.79 7.79 L 41.83 7.83 L 41.45 8.16 L 41.12 9.23 L 40.13 10.84 L 38.89 12.08 L 37.53 13.07 L 35.63 14.1 L 33.61 14.89 L 31.46 15.42 L 29.23 15.71 L 13.79 15.67 L 12.47 15.22 L 11.11 14.19 L 10.45 13.28 L 10.12 12.53 L 9.95 11.75 L 9.67 11.42 L 5.5 11.34 L 5.25 11.46 L 5.0 11.83 L 5.0 15.84 L 5.25 17.45 L 5.58 18.56 L 6.28 20.09 L 7.31 21.58 L 8.34 22.65 L 10.37 24.05 L 11.61 24.59 L 12.76 24.92 L 14.58 25.13 L 36.17 25.13 L 37.82 24.92 L 39.64 24.3 L 41.7 22.98 L 43.27 21.41 L 44.63 19.43 L 45.62 17.24 L 46.2 14.97 L 46.37 13.53 Z
  M 18.42 32.06 A 1.65 1.65 0 1 0 15.12 32.06 A 1.65 1.65 0 1 0 18.42 32.06 Z
`

export function BrandMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      focusable="false"
      aria-hidden="true"
      className={className}
    >
      <rect width="64" height="64" rx="4" fill="#0B3F3A" />
      <path d={BRAND_MARK_PATH} fill="#F6F1E7" fillRule="evenodd" />
    </svg>
  )
}
