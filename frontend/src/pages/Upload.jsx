import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, FileUp, X } from 'lucide-react'
import { documents, errorMessage, parser } from '../api/client'
import { Alert, Badge, Button, Card, titleCase } from '../components/ui'

const MAX_MB = 25
const ACCEPTED = ['application/pdf', 'image/jpeg', 'image/png']

// Mirrors the backend pipeline so the user sees where their document actually is.
const STAGES = [
  { key: 'uploaded', label: 'Uploaded' },
  { key: 'processing', label: 'Reading and parsing' },
  { key: 'done', label: 'Ready for review' },
]

export default function Upload() {
  const navigate = useNavigate()
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState('idle') // idle | uploading | processing | done
  const [documentId, setDocumentId] = useState(null)
  const [result, setResult] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)
  const pollRef = useRef(null)

  // Any interval must be cleared when the component unmounts, or it keeps
  // firing against a page that no longer exists.
  useEffect(() => () => clearInterval(pollRef.current), [])

  const reset = () => {
    clearInterval(pollRef.current)
    setFile(null)
    setError('')
    setProgress(0)
    setPhase('idle')
    setDocumentId(null)
    setResult(null)
  }

  const choose = useCallback((selected) => {
    setError('')
    if (!selected) return
    if (!ACCEPTED.includes(selected.type)) {
      setError('Only PDF, JPG and PNG files can be parsed.')
      return
    }
    if (selected.size > MAX_MB * 1024 * 1024) {
      setError(`That file is ${(selected.size / 1024 / 1024).toFixed(1)} MB. The limit is ${MAX_MB} MB.`)
      return
    }
    setFile(selected)
  }, [])

  // Poll for completion. The backend parses in a background task, so the
  // upload response arrives long before the data does.
  const watch = useCallback((id) => {
    let elapsed = 0
    pollRef.current = setInterval(async () => {
      elapsed += 2
      try {
        const { data } = await parser.status(id)
        if (data.is_complete) {
          clearInterval(pollRef.current)
          const { data: full } = await parser.result(id)
          setResult(full)
          setPhase('done')
        }
      } catch {
        // A single failed poll is not fatal - the next tick retries.
      }
      // Give up after two minutes rather than polling forever.
      if (elapsed > 120) {
        clearInterval(pollRef.current)
        setError('Processing is taking longer than expected. Check the Documents page.')
        setPhase('idle')
      }
    }, 2000)
  }, [])

  async function submit() {
    if (!file) return
    setError('')
    setPhase('uploading')
    setProgress(0)
    try {
      const { data } = await documents.upload(file, setProgress)
      setDocumentId(data.document.id)
      setPhase('processing')
      watch(data.document.id)
    } catch (err) {
      setPhase('idle')
      const detail = err?.response?.data?.detail
      if (detail?.code === 'duplicate_document') {
        setError(`This file was already uploaded as "${detail.existing_document_name}".`)
        setDocumentId(detail.existing_document_id)
      } else {
        setError(errorMessage(err, 'Upload failed'))
      }
    }
  }

  const stageIndex =
    phase === 'done' ? 2 : phase === 'processing' ? 1 : phase === 'uploading' ? 0 : -1

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">Upload a document</h1>
      <p className="mt-1 text-sm text-ink-faint">
        Bank statements, ITRs, GST returns, salary slips, invoices, balance sheets
        and P&amp;L statements. The type is detected automatically.
      </p>

      <Card className="mt-5 p-5">
        {phase === 'idle' && (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                choose(e.dataTransfer.files?.[0])
              }}
              onClick={() => inputRef.current?.click()}
              className={`cursor-pointer rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${
                dragging ? 'border-accent bg-accent-soft' : 'border-rule-strong hover:border-accent'
              }`}
            >
              <FileUp size={26} className="mx-auto text-ink-faint" />
              <p className="mt-3 text-sm font-medium text-ink">
                Drop a file here, or click to browse
              </p>
              <p className="mt-1 text-xs text-ink-faint">
                PDF, JPG or PNG &middot; up to {MAX_MB} MB
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                className="hidden"
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </div>

            {file && (
              <div className="mt-4 flex items-center justify-between rounded-md border border-rule bg-paper px-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{file.name}</p>
                  <p className="text-xs text-ink-faint">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <button
                  onClick={() => setFile(null)}
                  className="rounded p-1 text-ink-faint hover:text-fail"
                  title="Remove"
                >
                  <X size={16} />
                </button>
              </div>
            )}

            <div className="mt-4">
              <Alert>{error}</Alert>
            </div>

            <Button onClick={submit} disabled={!file} className="mt-4 w-full">
              Upload and parse
            </Button>
          </>
        )}

        {phase !== 'idle' && (
          <div className="py-2">
            <ol className="space-y-3">
              {STAGES.map((stage, index) => {
                const state =
                  index < stageIndex ? 'done' : index === stageIndex ? 'active' : 'todo'
                return (
                  <li key={stage.key} className="flex items-center gap-3">
                    <span
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${
                        state === 'done'
                          ? 'border-pass bg-pass-soft text-pass'
                          : state === 'active'
                            ? 'border-accent bg-accent-soft text-accent'
                            : 'border-rule text-ink-faint'
                      }`}
                    >
                      {state === 'done' ? <CheckCircle2 size={14} /> : index + 1}
                    </span>
                    <span
                      className={`text-sm ${
                        state === 'todo' ? 'text-ink-faint' : 'font-medium text-ink'
                      }`}
                    >
                      {stage.label}
                    </span>
                    {state === 'active' && phase === 'uploading' && (
                      <span className="tnum ml-auto text-xs text-ink-faint">
                        {progress}%
                      </span>
                    )}
                  </li>
                )
              })}
            </ol>

            {phase === 'uploading' && (
              <div className="mt-4 h-1 overflow-hidden rounded bg-rule">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}

            {phase === 'processing' && (
              <p className="mt-4 text-xs text-ink-faint">
                Reading the document and extracting fields. This usually takes
                10 to 20 seconds.
              </p>
            )}

            {phase === 'done' && result && (
              <div className="mt-5 rounded-md border border-rule bg-paper p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge status={result.document_type}>
                    {titleCase(result.document_type)}
                  </Badge>
                  <Badge status={result.validation_status} />
                  {result.confidence_score != null && (
                    <span className="tnum text-xs text-ink-faint">
                      {Math.round(result.confidence_score * 100)}% confidence
                    </span>
                  )}
                </div>
                <p className="mt-3 text-sm text-ink">
                  Extracted{' '}
                  {Object.values(result.effective_data || {}).filter(
                    (v) => v !== null && v !== '' && !(Array.isArray(v) && !v.length),
                  ).length}{' '}
                  fields
                  {result.validation_errors?.length
                    ? `, with ${result.validation_errors.length} to check`
                    : ' with no validation issues'}
                  .
                </p>
                <div className="mt-4 flex gap-2">
                  <Button onClick={() => navigate(`/documents/${documentId}`)}>
                    Review extracted data
                  </Button>
                  <Button variant="secondary" onClick={reset}>
                    Upload another
                  </Button>
                </div>
              </div>
            )}

            {error && (
              <div className="mt-4">
                <Alert>{error}</Alert>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
