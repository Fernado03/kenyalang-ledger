import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AccountantGate from './components/AccountantGate'

const ClientsPage = lazy(() => import('./pages/ClientsPage'))
const InboxPage = lazy(() => import('./pages/InboxPage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const ExportsPage = lazy(() => import('./pages/ExportsPage'))

function RouteFallback() {
  return (
    <div className="flex min-h-full flex-col gap-4 p-6">
      <div className="h-8 w-48 animate-pulse rounded-sm bg-surface-subtle" />
      <div className="h-6 w-full max-w-3xl animate-pulse rounded-sm bg-surface-subtle" />
      <div className="h-6 w-full max-w-2xl animate-pulse rounded-sm bg-surface-subtle" />
      <div className="h-6 w-full max-w-4xl animate-pulse rounded-sm bg-surface-subtle" />
    </div>
  )
}

function App() {
  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <AccountantGate>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/clients" element={<ClientsPage />} />
            <Route path="/clients/:clientId/inbox" element={<InboxPage />} />
            <Route
              path="/clients/:clientId/review/:receiptId"
              element={<ReviewPage />}
            />
            <Route
              path="/clients/:clientId/exports"
              element={<ExportsPage />}
            />
            <Route path="*" element={<Navigate to="/clients" replace />} />
          </Routes>
        </Suspense>
      </AccountantGate>
    </div>
  )
}

export default App
