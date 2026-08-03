import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Search, Trash2 } from 'lucide-react'
import { documents, errorMessage } from '../api/client'
import { useAuth } from '../context/AuthContext'
import {
  Alert, Badge, Button, Card, EmptyState, Input, Spinner,
  formatDateTime, titleCase,
} from '../components/ui'

const TYPES = [
  'bank_statement', 'itr', 'gst_return', 'salary_slip',
  'invoice', 'balance_sheet', 'profit_loss', 'unknown',
]
const STATUSES = [
  'uploaded', 'processing', 'parsed', 'validation_failed',
  'review_pending', 'approved', 'rejected',
]

export default function Documents() {
  const { isAdmin } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [filters, setFilters] = useState({ search: '', document_type: '', status: '' })

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, page_size: 20 }
      if (filters.search) params.search = filters.search
      if (filters.document_type) params.document_type = filters.document_type
      if (filters.status) params.status = filters.status
      const response = await documents.list(params)
      setData(response.data)
    } catch (err) {
      setError(errorMessage(err, 'Could not load documents'))
    } finally {
      setLoading(false)
    }
  }, [page, filters])

  useEffect(() => { load() }, [load])

  // Debounce the search box so typing "invoice" fires one request, not seven.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((prev) => (prev.search === searchInput ? prev : { ...prev, search: searchInput }))
      setPage(1)
    }, 400)
    return () => clearTimeout(timer)
  }, [searchInput])

  const setFilter = (key) => (event) => {
    setFilters((prev) => ({ ...prev, [key]: event.target.value }))
    setPage(1)
  }

  async function remove(id, name) {
    if (!window.confirm(`Delete "${name}"? This also removes its parsed data.`)) return
    try {
      await documents.remove(id)
      load()
    } catch (err) {
      setError(errorMessage(err, 'Could not delete'))
    }
  }

  const selectClass =
    'rounded-md border border-rule-strong bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none'

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Documents</h1>
          <p className="mt-1 text-sm text-ink-faint">
            {data ? `${data.total} document${data.total === 1 ? '' : 's'}` : 'Loading'}
          </p>
        </div>
        <Link to="/upload">
          <Button>Upload a document</Button>
        </Link>
      </div>

      <Card className="mb-4 p-3">
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
            />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search filename, PAN, GSTIN, invoice number, names"
              className="pl-9"
            />
          </div>
          <select value={filters.document_type} onChange={setFilter('document_type')} className={selectClass}>
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
          </select>
          <select value={filters.status} onChange={setFilter('status')} className={selectClass}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
        </div>
      </Card>

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      <Card>
        {loading ? (
          <Spinner label="Loading documents" />
        ) : !data?.items.length ? (
          <EmptyState
            title={filters.search || filters.document_type || filters.status
              ? 'No documents match these filters'
              : 'No documents yet'}
            description={filters.search || filters.document_type || filters.status
              ? 'Try clearing the filters to see everything.'
              : 'Upload a bank statement, invoice or salary slip to get started.'}
            action={<Link to="/upload"><Button>Upload a document</Button></Link>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">Document</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Uploaded</th>
                  <th className="px-4 py-2.5 text-right font-medium">Time</th>
                  {isAdmin && <th className="w-10 px-4 py-2.5" />}
                </tr>
              </thead>
              <tbody>
                {data.items.map((doc) => (
                  <tr key={doc.id} className="border-b border-rule last:border-0 hover:bg-paper">
                    <td className="px-4 py-3">
                      <Link to={`/documents/${doc.id}`} className="font-medium text-accent hover:underline">
                        {doc.document_name}
                      </Link>
                      <p className="text-xs text-ink-faint">
                        {doc.file_size_display} &middot; {doc.uploader?.name}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-ink-soft">
                      {doc.document_type ? titleCase(doc.document_type) : '-'}
                    </td>
                    <td className="px-4 py-3"><Badge status={doc.status} /></td>
                    <td className="px-4 py-3 text-ink-soft">{formatDateTime(doc.created_at)}</td>
                    <td className="tnum px-4 py-3 text-right text-ink-soft">
                      {doc.processing_time ? `${doc.processing_time.toFixed(1)}s` : '-'}
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3">
                        <button
                          onClick={() => remove(doc.id, doc.document_name)}
                          className="rounded p-1 text-ink-faint hover:bg-fail-soft hover:text-fail"
                          title="Delete"
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between border-t border-rule px-4 py-3">
            <p className="text-xs text-ink-faint">
              Page {data.page} of {data.total_pages}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={15} /> Previous
              </Button>
              <Button
                variant="secondary"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
