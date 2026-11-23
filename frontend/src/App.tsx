import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'
import AccountingPage from './pages/AccountingPage'
import CatalogPage from './pages/CatalogPage'
import CompanyVsActualPage from './pages/CompanyVsActualPage'
import DashboardPage from './pages/DashboardPage'
import HRPage from './pages/HRPage'
import LoginPage from './pages/LoginPage'
import PayoutPage from './pages/PayoutPage'
import PurchaseOrdersPage from './pages/PurchaseOrdersPage'
import SalesEntryPage from './pages/SalesEntryPage'
import SalesOrdersPage from './pages/SalesOrdersPage'
import SettlementsPage from './pages/SettlementsPage'
import ShopsPage from './pages/ShopsPage'
import WarehousesPage from './pages/WarehousesPage'

function PrivateRoute({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center text-slate-400">Loading...</div>
  if (!me) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
      <Route path="/company-vs-actual" element={<PrivateRoute><CompanyVsActualPage /></PrivateRoute>} />
      <Route path="/sales-entry" element={<PrivateRoute><SalesEntryPage /></PrivateRoute>} />
      <Route path="/settlements" element={<PrivateRoute><SettlementsPage /></PrivateRoute>} />
      <Route path="/dr-payout" element={<PrivateRoute><PayoutPage /></PrivateRoute>} />
      <Route path="/catalog" element={<PrivateRoute><CatalogPage /></PrivateRoute>} />
      <Route path="/warehouses" element={<PrivateRoute><WarehousesPage /></PrivateRoute>} />
      <Route path="/purchase-orders" element={<PrivateRoute><PurchaseOrdersPage /></PrivateRoute>} />
      <Route path="/shops" element={<PrivateRoute><ShopsPage /></PrivateRoute>} />
      <Route path="/sales-orders" element={<PrivateRoute><SalesOrdersPage /></PrivateRoute>} />
      <Route path="/accounting" element={<PrivateRoute><AccountingPage /></PrivateRoute>} />
      <Route path="/hr" element={<PrivateRoute><HRPage /></PrivateRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
