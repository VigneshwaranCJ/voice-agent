import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import CustomCursor from './components/CustomCursor'
import { ToastProvider } from './components/Toast'
import { AuthProvider, useAuth } from './hooks/useAuth'
import AppLayout from './layouts/AppLayout'
import { BusinessProfile, Integrations, Tenants } from './pages/Admin'
import Agents from './pages/Agents'
import BusinessData from './pages/BusinessData'
import { CallDetail, Calls } from './pages/Calls'
import FollowUps from './pages/FollowUps'
import Dashboard from './pages/Dashboard'
import Knowledge from './pages/Knowledge'
import Login from './pages/Login'
import Team from './pages/Team'

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading…</div>
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      <CustomCursor />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><AppLayout /></Protected>}>
            <Route index element={<Dashboard />} />
            <Route path="agents" element={<Agents />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="calls" element={<Calls />} />
            <Route path="calls/:id" element={<CallDetail />} />
            <Route path="follow-ups" element={<FollowUps />} />
            <Route path="data" element={<BusinessData />} />
            <Route path="team" element={<Team />} />
            <Route path="integrations" element={<Integrations />} />
            <Route path="business" element={<BusinessProfile />} />
            <Route path="tenants" element={<Tenants />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  )
}
