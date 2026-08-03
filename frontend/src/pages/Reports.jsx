import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, FileDown, FileText } from 'lucide-react'
import { errorMessage, reports } from '../api/client'
import {
  Alert, Badge, Button, Card, EmptyState, Spinner, formatDateTime, titleCase,
} from '../components/ui'

const REVIEW_STATES = ['pending', 'approved', 'rejected']

export default function Reports() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reviewStatus, setReviewStatus] = useState('')
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page: 1, page_size: 50 }
      if (reviewStatus) params.review_status = reviewStatus
      const response = await reports.list(params)
      setData(response.data)
    } catch (err) {
      setError(errorMessage(err, 'Could not load reports'))
    } finally {
      setLoading(false)
    }
  }, [reviewStatus])

  useEffect(() => { load() }, [load])

  async function download(id, format, name) {
    setBusy(`${id}-${format}`)
    setError('')
    try {
      const ext = format === 'excel' ? 'xlsx' : format
      await reports.download(id, format, `${name}_report.${ext}`)
    } catch (err) {
      setError(errorMessage(err, 'Could not download the report'))
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Reports</h1>
          <p className="mt-1 text-sm text-ink-faint">
            Download extracted data as Excel, PDF or CSV
            {data ? ` · ${data.total} parsed` : ''}
          </p>
        </div>
        <select
          value={reviewStatus}
          onChange={(e) => setReviewStatus(e.target.value)}
          className="rounded-md border border-rule-strong bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
        >
          <option value="">All review states</option>
          {REVIEW_STATES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </select>
      </div>

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      <Card>
        {loading ? (
          <Spinner label="Loading reports" />
        ) : !data?.items.length ? (
          <EmptyState
            title="No parsed documents yet"
            description="Reports become available once a document finishes processing."
            action={<Link to="/upload"><Button>Upload a document</Button></Link>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">Document</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Validation</th>
                  <th className="px-4 py-2.5 font-medium">Review</th>
                  <th className="px-4 py-2.5 text-right font-medium">Fields</th>
                  <th className="px-4 py-2.5 text-right font-medium">Confidence</th>
                  <th className="px-4 py-2.5 font-medium">Parsed</th>
                  <th className="px-4 py-2.5 text-right font-medium">Download</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.document_id} className="border-b border-rule last:border-0 hover:bg-paper">
                    <td className="px-4 py-3">
                      <Link
                        to={`/documents/${row.document_id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {row.document_name}
                      </Link>
                      <p className="text-xs text-ink-faint">{row.uploader_name}</p>
                    </td>
                    <td className="px-4 py-3 text-ink-soft">
                      {row.document_type ? titleCase(row.document_type) : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <Badge status={row.validation_status} />
                      {row.issue_count > 0 && (
                        <span className="ml-1.5 text-xs text-flag">{row.issue_count}</span>
                      )}
                    </td>
                    <td className="px-4 py-3"><Badge status={row.review_status} /></td>
                    <td className="tnum px-4 py-3 text-right text-ink-soft">{row.field_count}</td>
                    <td className="tnum px-4 py-3 text-right text-ink-soft">
                      {row.confidence_score != null
                        ? `${Math.round(row.confidence_score * 100)}%`
                        : '-'}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-ink-soft">
                      {formatDateTime(row.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => download(row.document_id, 'excel', row.document_name)}
                          disabled={busy === `${row.document_id}-excel`}
                          className="rounded p-1.5 text-ink-faint hover:bg-accent-soft hover:text-accent disabled:opacity-40"
                          title="Excel"
                        >
                          <FileDown size={15} />
                        </button>
                        <button
                          onClick={() => download(row.document_id, 'pdf', row.document_name)}
                          disabled={busy === `${row.document_id}-pdf`}
                          className="rounded p-1.5 text-ink-faint hover:bg-accent-soft hover:text-accent disabled:opacity-40"
                          title="PDF"
                        >
                          <FileText size={15} />
                        </button>
                        <button
                          onClick={() => download(row.document_id, 'csv', row.document_name)}
                          disabled={busy === `${row.document_id}-csv`}
                          className="rounded p-1.5 text-ink-faint hover:bg-accent-soft hover:text-accent disabled:opacity-40"
                          title="CSV"
                        >
                          <Download size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
