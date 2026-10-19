import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest does not expose `afterEach` as a global here, so Testing Library
// cannot register its own auto-cleanup; unmount between tests explicitly.
afterEach(() => {
  cleanup()
})
