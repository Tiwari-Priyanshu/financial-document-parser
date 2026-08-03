import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Check, Download, FileDown, RotateCcw, X,
} from 'lucide-react'
import { errorMessage, logs, parser, reports } from '../api/client'
import {
  Alert, Badge, Button, Card, Input, Spinner,
  formatAmount, formatDateTime, titleCase,
} from '../components/ui'

// Identifiers where character-level accuracy decides correctness. These render
// in monospace so 0/O and 1/I are distinguishable - the exact misreads the
// backend's checksum validation catches.
const IDENTIFIER_VALIDATORS = new Set(['pan', 'gstin', 'ifsc', 'account_number'])

export default function Review() {
  const { id } = useParams()
  const [result, setResult] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [edits, setEdits] = useState({})
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState('')
  const [showRaw, setShowRaw] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const { data } = await parser.result(id)
      setResult(data)
      setEdits({})
      const trail = await logs.forDocument(id).catch(() => ({ data: [] }))
      setTimeline(trail.data || [])
    } catch (err) {
      setError(errorMessage(err, 'Could not load this document'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  // Index validation issues by field so each row can show its own message.
  const issuesByField = useMemo(() => {
    const map = {}
    for (const issue of result?.validation_errors || []) {
      ;(map[issue.field] ||= []).push(issue)
    }
    return map
  }, [result])

  const data = result?.effective_data || {}
  const dirty = Object.keys(edits).length > 0

  const valueFor = (name) => (name in edits ? edits[name] : data[name])

  async function save() {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const corrections = {}
      for (const [key, value] of Object.entries(edits)) {
        corrections[key] = value === '' ? null : value
      }
      const { data: updated } = await parser.updateFields(id, corrections, 'Manual correction')
      setResult(updated)
      setEdits({})
      setNotice('Corrections saved and re-validated.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save corrections'))
    } finally {
      setSaving(false)
    }
  }

  async function decide(action) {
    const remarks =
      action === 'reject'
        ? window.prompt('Why is this being rejected?')
        : window.prompt('Any remarks? (optional)') || 'Verified'
    if (action === 'reject' && !remarks) return

    setBusy(action)
    setError('')
    try {
      const { data: updated } = await parser[action](id, remarks)
      setResult(updated)
      setNotice(action === 'approve' ? 'Document approved.' : 'Parse rejected.')
      logs.forDocument(id).then((r) => setTimeline(r.data || [])).catch(() => {})
    } catch (err) {
      setError(errorMessage(err, `Could not ${action}`))
    } finally {
      setBusy('')
    }
  }

  async function reprocess() {
    setBusy('reprocess')
    try {
      await parser.reprocess(id)
      setNotice('Reprocessing. This page will refresh in a few seconds.')
      setTimeout(load, 12000)
    } catch (err) {
      setError(errorMessage(err, 'Could not reprocess'))
    } finally {
      setBusy('')
    }
  }

  async function download(format) {
    setBusy(format)
    try {
      const ext = format === 'excel' ? 'xlsx' : format
      await reports.download(id, format, `${result.document_name}_report.${ext}`)
    } catch (err) {
      setError(errorMessage(err, 'Could not download the report'))
    } finally {
      setBusy('')
    }
  }

  if (loading) return <Spinner label="Loading document" />
  if (!result) {
    return (
      <div className="mx-auto max-w-lg py-12">
        <Alert>{error || 'Document not found'}</Alert>
        <Link to="/documents" className="mt-4 inline-block text-sm text-accent hover:underline">
          Back to documents
        </Link>
      </div>
    )
  }

  const decided = ['approved', 'rejected'].includes(result.review_status)

  return (
    <div>
      <Link
        to="/documents"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink"
      >
        <ArrowLeft size={15} /> Documents
      </Link>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold text-ink">{result.document_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge status={result.document_type}>{titleCase(result.document_type)}</Badge>
            <Badge status={result.status} />
            <Badge status={result.validation_status} />
            {result.confidence_score != null && (
              <span className="tnum text-xs text-ink-faint">
                {Math.round(result.confidence_score * 100)}% confidence
              </span>
            )}
            {result.processing_time && (
              <span className="tnum text-xs text-ink-faint">
                {result.processing_time.toFixed(1)}s
              </span>
            )}
            {result.extraction_method && (
              <span className="text-xs text-ink-faint">
                via {result.extraction_method.replace('_', ' ')}
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" loading={busy === 'excel'} onClick={() => download('excel')}>
            <FileDown size={15} /> Excel
          </Button>
          <Button variant="secondary" loading={busy === 'pdf'} onClick={() => download('pdf')}>
            <Download size={15} /> PDF
          </Button>
          <Button variant="secondary" loading={busy === 'csv'} onClick={() => download('csv')}>
            CSV
          </Button>
          <Button variant="secondary" loading={busy === 'reprocess'} onClick={reprocess}>
            <RotateCcw size={15} /> Reprocess
          </Button>
        </div>
      </div>

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="pass">{notice}</Alert></div>}

      {result.validation_errors?.length > 0 && (
        <Card className="mb-4 border-flag/30 bg-flag-soft p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-flag" />
            <div>
              <p className="text-sm font-medium text-flag">
                {result.validation_errors.length} field
                {result.validation_errors.length === 1 ? '' : 's'} need checking
              </p>
              <ul className="mt-1.5 space-y-1 text-sm text-ink-soft">
                {result.validation_errors.map((issue, index) => (
                  <li key={index}>
                    <span className="font-medium">{titleCase(issue.field)}:</span>{' '}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <div className="flex items-center justify-between border-b border-rule px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">Extracted fields</h2>
              {dirty && (
                <Button loading={saving} onClick={save}>
                  Save {Object.keys(edits).length} change
                  {Object.keys(edits).length === 1 ? '' : 's'}
                </Button>
              )}
            </div>

            <div className="divide-y divide-rule">
              {result.field_definitions.map((field) => {
                const issues = issuesByField[field.name] || []
                const hasError = issues.some((i) => i.severity === 'error')
                const value = valueFor(field.name)
                const isIdentifier = IDENTIFIER_VALIDATORS.has(field.validator)
                const changed = field.name in edits

                if (field.type === 'array') {
                  const items = Array.isArray(value) ? value : []
                  return (
                    <div key={field.name} className="px-4 py-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                        {field.label}
                      </p>
                      {items.length === 0 ? (
                        <p className="mt-1 text-sm text-ink-faint">None extracted</p>
                      ) : (
                        <div className="mt-2 overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-rule text-left text-xs text-ink-faint">
                                {Object.keys(items[0]).map((key) => (
                                  <th key={key} className="py-1.5 pr-4 font-medium">
                                    {titleCase(key)}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {items.map((item, index) => (
                                <tr key={index} className="border-b border-rule last:border-0">
                                  {Object.entries(item).map(([key, cell]) => (
                                    <td
                                      key={key}
                                      className={`py-1.5 pr-4 ${
                                        typeof cell === 'number' ? 'tnum' : ''
                                      }`}
                                    >
                                      {typeof cell === 'number' ? formatAmount(cell) : cell ?? '-'}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )
                }

                return (
                  <div
                    key={field.name}
                    className={`grid gap-2 px-4 py-2.5 sm:grid-cols-[200px_1fr] sm:items-center ${
                      hasError ? 'bg-fail-soft' : issues.length ? 'bg-flag-soft' : ''
                    }`}
                  >
                    <div>
                      <span className="text-sm text-ink-soft">{field.label}</span>
                      {field.mandatory && <span className="ml-1 text-fail">*</span>}
                    </div>
                    <div>
                      <Input
                        value={value ?? ''}
                        onChange={(e) =>
                          setEdits((prev) => ({ ...prev, [field.name]: e.target.value }))
                        }
                        disabled={decided}
                        placeholder="Not found"
                        className={`${isIdentifier ? 'ident uppercase' : ''} ${
                          field.type === 'number' ? 'tnum' : ''
                        } ${changed ? 'border-accent bg-accent-soft' : ''}`}
                      />
                      {issues.map((issue, index) => (
                        <p
                          key={index}
                          className={`mt-1 text-xs ${
                            issue.severity === 'error' ? 'text-fail' : 'text-flag'
                          }`}
                        >
                          {issue.message}
                        </p>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>

            {!decided && (
              <div className="flex flex-wrap gap-2 border-t border-rule px-4 py-3">
                <Button loading={busy === 'approve'} onClick={() => decide('approve')}>
                  <Check size={15} /> Approve
                </Button>
                <Button
                  variant="danger"
                  loading={busy === 'reject'}
                  onClick={() => decide('reject')}
                >
                  <X size={15} /> Reject
                </Button>
                {dirty && (
                  <span className="self-center text-xs text-flag">
                    Save your changes before approving
                  </span>
                )}
              </div>
            )}

            {decided && (
              <div className="border-t border-rule px-4 py-3 text-sm text-ink-soft">
                <Badge status={result.review_status} />
                {result.reviewer_name && (
                  <span className="ml-2">by {result.reviewer_name}</span>
                )}
                {result.remarks && (
                  <p className="mt-1 text-xs text-ink-faint">{result.remarks}</p>
                )}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="border-b border-rule px-4 py-3 text-sm font-semibold text-ink">
              Processing timeline
            </h2>
            <ol className="space-y-3 px-4 py-3">
              {timeline.length === 0 && (
                <li className="text-sm text-ink-faint">No entries recorded</li>
              )}
              {timeline.map((entry) => (
                <li key={entry.id} className="flex gap-2.5">
                  <span
                    className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                      entry.status === 'failure' ? 'bg-fail' : 'bg-pass'
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-ink">{titleCase(entry.action)}</p>
                    {entry.remarks && (
                      <p className="text-xs text-ink-faint">{entry.remarks}</p>
                    )}
                    <p className="tnum text-xs text-ink-faint">
                      {formatDateTime(entry.created_at)}
                      {entry.processing_time ? ` · ${entry.processing_time.toFixed(2)}s` : ''}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card>
            <button
              onClick={() => setShowRaw((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-ink"
            >
              Source text
              <span className="text-xs font-normal text-ink-faint">
                {showRaw ? 'Hide' : 'Show'}
              </span>
            </button>
            {showRaw && (
              <pre className="max-h-96 overflow-auto border-t border-rule px-4 py-3 text-xs leading-relaxed text-ink-soft">
                {result.raw_text || 'No text stored'}
              </pre>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
