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
    <div className="page-shell" role="status" aria-busy="true">
      <span className="sr-only">Loading page</span>
      <div className="border-b border-border pb-7">
        <div className="skeleton h-3 w-28" />
        <div className="skeleton mt-4 h-9 w-64" />
        <div className="skeleton mt-3 h-4 w-96 max-w-full" />
      </div>
      <div className="mt-8 space-y-3">
        <div className="skeleton h-11 w-full" />
        <div className="skeleton h-11 w-full" />
        <div className="skeleton h-11 w-2/3" />
      </div>
    </div>
  )
}

/** Authenticated chrome shared by every route: gate, skip link, lazy boundary. */
function RootLayout() {
  return (
    <div className="min-h-dvh bg-canvas text-text-primary">
      <AccountantGate>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:h-11 focus:items-center focus:border focus:border-border-strong focus:border-l-2 focus:border-l-brand-900 focus:bg-surface focus:px-4 focus:text-ui focus:font-semibold focus:text-text-primary"
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
