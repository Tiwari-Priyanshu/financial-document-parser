import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout, { ProtectedRoute } from './components/Layout'
import Login from './pages/Login'

function Placeholder({ name }) {
  return (
    <div className="rounded-lg border border-dashed border-rule-strong bg-surface px-6 py-16 text-center">
      <p className="text-sm font-medium text-ink">{name}</p>
      <p className="mt-1 text-sm text-ink-faint">Coming next.</p>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login mode="login" />} />
          <Route path="/register" element={<Login mode="register" />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route index element={<Placeholder name="Dashboard" />} />
              <Route path="upload" element={<Placeholder name="Upload" />} />
              <Route path="documents" element={<Placeholder name="Documents" />} />
              <Route path="documents/:id" element={<Placeholder name="Review" />} />
              <Route path="reports" element={<Placeholder name="Reports" />} />
              <Route path="logs" element={<Placeholder name="Audit log" />} />
            </Route>
          </Route>

          <Route path="*" element={<Placeholder name="Page not found" />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
