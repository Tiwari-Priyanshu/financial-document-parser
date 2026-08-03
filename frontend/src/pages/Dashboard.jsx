import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { dashboard, errorMessage } from '../api/client'
import {
  Alert, Button, Card, EmptyState, Spinner, formatDateTime, titleCase,
} from '../components/ui'

const TYPE_COLORS = [
  '#1b4d8f', '#2f6fb8', '#4a90d9', '#b45309',
  '#15803d', '#7c3aed', '#0891b2',
]

function Metric({ label, value, sub, tone = 'ink' }) {
  const tones = { ink: 'text-ink', pass: 'text-pass', fail: 'text-fail', flag: 'text-flag' }
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-ink-faint">{label}</p>
      <p className={`tnum mt-1.5 text-2xl font-semibold ${tones[tone]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-faint">{sub}</p>}
    </Card>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    dashboard
      .stats(30)
      .then((res) => setStats(res.data))
      .catch((err) => setError(errorMessage(err, 'Could not load the dashboard')))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner label="Loading dashboard" />
  if (error) return <Alert>{error}</Alert>

  const empty = stats.total_documents === 0

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
          <p className="mt-1 text-sm text-ink-faint">Processing activity over the last 30 days</p>
        </div>
        <Link to="/upload"><Button>Upload a document</Button></Link>
      </div>

      {empty ? (
        <Card>
          <EmptyState
            title="Nothing processed yet"
            description="Upload a financial document and the numbers will appear here."
            action={<Link to="/upload"><Button>Upload a document</Button></Link>}
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Metric label="Total" value={stats.total_documents} sub="documents uploaded" />
            <Metric label="Parsed" value={stats.successfully_parsed} tone="pass" sub="extracted successfully" />
            <Metric label="Failed" value={stats.failed_parsing} tone={stats.failed_parsing ? 'fail' : 'ink'} sub="needs attention" />
            <Metric label="Success rate" value={`${stats.success_rate}%`} tone={stats.success_rate >= 80 ? 'pass' : 'flag'} sub="of completed documents" />
            <Metric label="Avg. time" value={`${stats.average_processing_time.toFixed(1)}s`} sub="per document" />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">Documents by type</h2>
              {stats.documents_by_type.length === 0 ? (
                <p className="py-8 text-center text-sm text-ink-faint">No types classified yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart
                    data={stats.documents_by_type.map((d) => ({ ...d, name: titleCase(d.label) }))}
                    layout="vertical"
                    margin={{ left: 10, right: 16 }}
                  >
                    <CartesianGrid horizontal={false} stroke="#e2e6ed" />
                    <XAxis type="number" allowDecimals={false} stroke="#8794a5" fontSize={11} />
                    <YAxis type="category" dataKey="name" width={110} stroke="#8794a5" fontSize={11} />
                    <Tooltip
                      cursor={{ fill: '#f7f8fa' }}
                      contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e2e6ed' }}
                    />
                    <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                      {stats.documents_by_type.map((_, index) => (
                        <Cell key={index} fill={TYPE_COLORS[index % TYPE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">Daily uploads</h2>
              {stats.daily_uploads.length === 0 ? (
                <p className="py-8 text-center text-sm text-ink-faint">No uploads in this window</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={stats.daily_uploads} margin={{ left: -18, right: 12, top: 8 }}>
                    <CartesianGrid stroke="#e2e6ed" />
                    <XAxis
                      dataKey="period"
                      stroke="#8794a5"
                      fontSize={11}
                      tickFormatter={(v) => v.slice(5)}
                    />
                    <YAxis allowDecimals={false} stroke="#8794a5" fontSize={11} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e2e6ed' }} />
                    <Line
                      type="monotone"
                      dataKey="count"
                      stroke="#1b4d8f"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <h2 className="border-b border-rule px-4 py-3 text-sm font-semibold text-ink">
                Recent activity
              </h2>
              <ul className="divide-y divide-rule">
                {stats.recent_activity.slice(0, 10).map((entry, index) => (
                  <li key={index} className="flex items-start gap-2.5 px-4 py-2.5">
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        entry.status === 'failure' ? 'bg-fail' : 'bg-pass'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-ink">
                        {titleCase(entry.action)}
                        {entry.document_name && (
                          <span className="text-ink-faint"> · {entry.document_name}</span>
                        )}
                      </p>
                      {entry.remarks && (
                        <p className="truncate text-xs text-ink-faint">{entry.remarks}</p>
                      )}
                    </div>
                    <span className="tnum shrink-0 text-xs text-ink-faint">
                      {formatDateTime(entry.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">By status</h2>
              <ul className="space-y-2">
                {stats.documents_by_status.map((row) => (
                  <li key={row.label} className="flex items-center justify-between text-sm">
                    <span className="text-ink-soft">{titleCase(row.label)}</span>
                    <span className="tnum font-medium text-ink">{row.count}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 border-t border-rule pt-3">
                <p className="text-xs text-ink-faint">Awaiting review</p>
                <p className="tnum text-lg font-semibold text-flag">{stats.pending_review}</p>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
