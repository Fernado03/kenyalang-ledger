import { Suspense, lazy } from 'react'
import {
  Navigate,
  Outlet,
  RouterProvider,
  createBrowserRouter,
} from 'react-router-dom'
import AccountantGate from './components/AccountantGate'

const ClientsPage = lazy(() => import('./pages/ClientsPage'))
const InboxPage = lazy(() => import('./pages/InboxPage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const ExportsPage = lazy(() => import('./pages/ExportsPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const UploadPage = lazy(() => import('./pages/UploadPage'))

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

/** Authenticated chrome shared by every route: gate, skip link, lazy boundary. */
function RootLayout() {
  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <AccountantGate>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:h-11 focus:items-center focus:border focus:border-border focus:bg-surface focus:px-4 focus:text-sm focus:font-semibold focus:text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-900"
        >
          Skip to content
        </a>
        <main id="main-content" tabIndex={-1}>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </main>
      </AccountantGate>
    </div>
  )
}

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/clients', element: <ClientsPage /> },
      { path: '/clients/:clientId/inbox', element: <InboxPage /> },
      {
        path: '/clients/:clientId/review/:receiptId',
        element: <ReviewPage />,
      },
      { path: '/clients/:clientId/exports', element: <ExportsPage /> },
      { path: '/clients/:clientId/dashboard', element: <DashboardPage /> },
      { path: '/upload', element: <UploadPage /> },
      { path: '*', element: <Navigate to="/clients" replace /> },
    ],
  },
])

function App() {
  return <RouterProvider router={router} />
}

export default App
