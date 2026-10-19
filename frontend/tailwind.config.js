/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral Slate Foundation (High contrast, clean borders)
        canvas: '#F8FAFC', // Slate 50
        surface: '#FFFFFF', // Pure White
        'surface-subtle': '#F1F5F9', // Slate 100
        border: '#CBD5E1', // Slate 300 (Crisp, defined outlines)
        'border-focus': '#0F172A', // Slate 900

        // Typography
        'text-primary': '#0F172A', // Slate 900
        'text-secondary': '#475569', // Slate 600
        'text-muted': '#475569', // Slate 600 (>= 4.5:1 on white and surface-subtle)

        // Brand Wedge: Sarawak Hornbill Teal (Single intentional accent)
        brand: {
          50: '#F0FDFA',
          500: '#14B8A6',
          700: '#0F766E',
          900: '#134E4A', // Primary active brand color
        },

        // Semantic confidence & financial status tokens. Text/background pairs are
        // chosen for legibility; this project makes no formal WCAG conformance claim.
        verified: {
          bg: '#ECFDF5', // Emerald 50
          border: '#10B981', // Emerald 500
          text: '#065F46', // Emerald 800
        },
        warning: {
          bg: '#FFFBEB', // Amber 50 (Low-confidence OCR)
          border: '#F59E0B', // Amber 500
          text: '#92400E', // Amber 800
        },
        mismatch: {
          bg: '#FEF2F2', // Red 50 (Math reconciliation failure)
          border: '#EF4444', // Red 500
          text: '#991B1B', // Red 800
        },
      },
      fontFamily: {
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
      },
      height: {
        'dense-row': '40px',
      },
    },
  },
  plugins: [],
}
