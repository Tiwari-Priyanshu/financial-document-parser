import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { errorMessage, logs } from '../api/client'
import {
  Alert, Badge, Button, Card, EmptyState, Spinner, formatDateTime, titleCase,
} from '../components/ui'

const ACTIONS = [
  'document_uploaded', 'ocr_completed', 'classification_completed',
  'parsing_completed', 'parsing_failed', 'validation_passed',
  'validation_failed', 'fields_edited', 'document_approved',
  'document_rejected', 'report_generated', 'user_login', 'user_registered',
]

export default function Logs() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: 50 }
      if (action) params.action = action
      const response = await logs.list(params)
      setData(response.data)
    } catch (err) {
      setError(errorMessage(err, 'Could not load the audit log'))
    } finally {
      setLoading(false)
    }
  }, [page, action])

  useEffect(() => { load() }, [load])

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Audit log</h1>
          <p className="mt-1 text-sm text-ink-faint">
            Every action recorded, newest first
            {data ? ` · ${data.total} entries` : ''}
          </p>
        </div>
        <select
          value={action}
          onChange={(e) => { setAction(e.target.value); setPage(1) }}
          className="rounded-md border border-rule-strong bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
        >
          <option value="">All actions</option>
          {ACTIONS.map((a) => <option key={a} value={a}>{titleCase(a)}</option>)}
        </select>
      </div>

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      <Card>
        {loading ? (
          <Spinner label="Loading audit log" />
        ) : !data?.items.length ? (
          <EmptyState
            title="No entries yet"
            description="Actions are recorded here as documents move through the pipeline."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Action</th>
                  <th className="px-4 py-2.5 font-medium">Document</th>
                  <th className="px-4 py-2.5 font-medium">By</th>
                  <th className="px-4 py-2.5 font-medium">Details</th>
                  <th className="px-4 py-2.5 text-right font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((entry) => (
                  <tr key={entry.id} className="border-b border-rule last:border-0 hover:bg-paper">
                    <td className="tnum whitespace-nowrap px-4 py-2.5 text-ink-soft">
                      {formatDateTime(entry.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge status={entry.status === 'failure' ? 'failed' : 'passed'}>
                        {titleCase(entry.action)}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      {entry.document_id ? (
                        <Link
                          to={`/documents/${entry.document_id}`}
                          className="text-accent hover:underline"
                        >
                          {entry.document_name || 'View'}
                        </Link>
                      ) : (
                        <span className="text-ink-faint">-</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-ink-soft">{entry.user_name || '-'}</td>
                    <td className="max-w-md px-4 py-2.5 text-ink-faint">
                      {entry.remarks || '-'}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-soft">
                      {entry.processing_time ? `${entry.processing_time.toFixed(2)}s` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between border-t border-rule px-4 py-3">
            <p className="text-xs text-ink-faint">Page {data.page} of {data.total_pages}</p>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={15} /> Previous
              </Button>
              <Button variant="secondary" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>
                Next <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
