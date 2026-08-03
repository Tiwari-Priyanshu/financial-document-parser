import { AlertCircle, Loader2 } from 'lucide-react'

/** Validation and processing states share one visual vocabulary across the app. */
const TONES = {
  pass: 'bg-pass-soft text-pass border-pass/20',
  flag: 'bg-flag-soft text-flag border-flag/20',
  fail: 'bg-fail-soft text-fail border-fail/20',
  accent: 'bg-accent-soft text-accent border-accent/20',
  neutral: 'bg-paper text-ink-soft border-rule',
}

const STATUS_TONE = {
  approved: 'pass',
  passed: 'pass',
  parsed: 'pass',
  review_pending: 'flag',
  pending: 'flag',
  partial: 'flag',
  processing: 'accent',
  uploaded: 'accent',
  rejected: 'fail',
  validation_failed: 'fail',
  failed: 'fail',
}

export function Badge({ status, children, tone }) {
  const resolved = tone || STATUS_TONE[status] || 'neutral'
  const label = children || String(status || '').replace(/_/g, ' ')
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium capitalize ${TONES[resolved]}`}
    >
      {label}
    </span>
  )
}

export function Card({ children, className = '' }) {
  return (
    <div className={`rounded-lg border border-rule bg-surface ${className}`}>
      {children}
    </div>
  )
}

export function Button({
  children, variant = 'primary', loading, className = '', ...props
}) {
  const variants = {
    primary: 'bg-accent text-white hover:bg-accent/90 disabled:bg-accent/40',
    secondary: 'border border-rule-strong bg-surface text-ink hover:bg-paper',
    danger: 'border border-fail/30 bg-fail-soft text-fail hover:bg-fail/10',
    ghost: 'text-ink-soft hover:bg-paper hover:text-ink',
  }
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${variants[variant]} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  )
}

export function Field({ label, hint, error, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink-faint">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-fail">{error}</span>}
    </label>
  )
}

export function Input({ className = '', ...props }) {
  return (
    <input
      className={`w-full rounded-md border border-rule-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none ${className}`}
      {...props}
    />
  )
}

export function Alert({ children, tone = 'fail' }) {
  if (!children) return null
  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2.5 text-sm ${TONES[tone]}`}
      role="alert"
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-ink-faint">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  )
}

/**
 * An empty screen is an invitation to act, not a dead end - so this always
 * takes an action rather than just stating that nothing is here.
 */
export function EmptyState({ title, description, action }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && (
        <p className="mx-auto mt-1 max-w-sm text-sm text-ink-faint">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleDateString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
      })
    : '-'

export const formatDateTime = (value) =>
  value
    ? new Date(value).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : '-'

/** Indian numbering: 12,34,567 rather than 1,234,567. */
export const formatAmount = (value) =>
  typeof value === 'number'
    ? value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value ?? '-'

export const titleCase = (value) =>
  String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
