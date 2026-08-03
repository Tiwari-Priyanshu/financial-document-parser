import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Alert, Button, Field, Input } from '../components/ui'

export default function Login({ mode = 'login' }) {
  const isRegister = mode === 'register'
  const { user, login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={location.state?.from || '/'} replace />

  const update = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setError('')
    setBusy(true)
    const result = isRegister
      ? await register(form.name, form.email, form.password)
      : await login(form.email, form.password)
    setBusy(false)
    if (result.ok) navigate('/', { replace: true })
    else setError(result.error)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded bg-accent">
            <FileText size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight text-ink">
              Financial Document Parser
            </p>
            <p className="text-xs text-ink-faint">Extraction and review workspace</p>
          </div>
        </div>

        <div className="rounded-lg border border-rule bg-surface p-6">
          <h1 className="text-lg font-semibold text-ink">
            {isRegister ? 'Create an account' : 'Sign in'}
          </h1>
          <p className="mt-1 text-sm text-ink-faint">
            {isRegister
              ? 'The first account created becomes the administrator.'
              : 'Use the email and password you registered with.'}
          </p>

          <form onSubmit={submit} className="mt-5 space-y-4">
            {isRegister && (
              <Field label="Full name">
                <Input
                  value={form.name}
                  onChange={update('name')}
                  required
                  minLength={2}
                  autoComplete="name"
                  placeholder="Priyanshu Tiwari"
                />
              </Field>
            )}

            <Field label="Email">
              <Input
                type="email"
                value={form.email}
                onChange={update('email')}
                required
                autoComplete="email"
                placeholder="you@company.com"
              />
            </Field>

            <Field
              label="Password"
              hint={isRegister ? 'At least 8 characters, with a letter and a digit' : null}
            >
              <Input
                type="password"
                value={form.password}
                onChange={update('password')}
                required
                minLength={isRegister ? 8 : undefined}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
              />
            </Field>

            <Alert>{error}</Alert>

            <Button type="submit" loading={busy} className="w-full">
              {isRegister ? 'Create account' : 'Sign in'}
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-ink-faint">
            {isRegister ? 'Already have an account? ' : 'No account yet? '}
            <Link
              to={isRegister ? '/login' : '/register'}
              className="font-medium text-accent hover:underline"
            >
              {isRegister ? 'Sign in' : 'Create one'}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
