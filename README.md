# AI Financial Document Parser

Upload an Indian financial document — bank statement, ITR, GST return, salary slip, invoice, balance sheet or P&L — and the system identifies what it is, extracts the fields that matter, checks them for internal consistency, and routes anything doubtful to a human before it becomes a report.

**Live application:** https://financial-document-parser-phi.vercel.app
**API:** https://findoc-api-l3nq.onrender.com
**Interactive API docs:** https://findoc-api-l3nq.onrender.com/docs
**Architecture and schema diagrams:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

> The API runs on Render's free tier and sleeps after 15 minutes idle. The first request after a gap takes roughly 50 seconds to wake the service.

---

## Overview

Accounting firms and lenders receive thousands of financial documents daily and re-key them by hand. This system automates the extraction while keeping a human in the loop where it counts.

What makes it a *financial* parser rather than a generic text extractor is the validation layer. Every extracted number is checked twice:

**Format validation** — a PAN's fourth character encodes the holder type; a GSTIN carries a mod-36 check digit; an IFSC has a mandatory `0` in position 5. These catch the exact misreads OCR produces on a poor scan, where `O` becomes `0` and `S` becomes `5`.

**Arithmetic validation** — 15 cross-field checks across the seven document types. A bank statement's opening balance plus credits minus debits must land on the closing balance. A balance sheet must satisfy assets = liabilities + equity. CGST must equal SGST on an intra-state supply. Every individual field can look perfectly valid while the numbers disagree, and that disagreement is the signal that something was read wrong.

### The main engineering decision

Most Indian financial PDFs are *digitally generated*, not scanned — net banking statements, GST portal downloads, ITR acknowledgements, Tally invoices. They carry a real text layer.

So the pipeline tries the cheap path first:

| Input | Method | Cost | Time |
|---|---|---|---|
| PDF with a text layer | pdfplumber | free | ~50 ms |
| Scanned PDF or image | Gemini vision | 1 API call | ~5 s |

On a realistic document mix this keeps most uploads off the API entirely, which matters on a free tier with per-minute rate limits — and reading the embedded text is *more* accurate than a model interpreting pixels, not less.

---

## Tech stack

**Backend** — FastAPI · Python 3.12 · MongoDB Atlas with Beanie ODM · JWT (python-jose) · bcrypt · pdfplumber · pypdf · Pillow · openpyxl · ReportLab

**Frontend** — React 19 · Vite 8 · Tailwind CSS 4 · React Router 7 · Axios · Recharts · lucide-react

**AI / OCR** — Google Gemini 3.6 Flash for classification, extraction and fallback OCR

**Deployment** — Vercel (frontend) · Render (backend) · MongoDB Atlas M0, Mumbai

---

## Features

- Registration, login, JWT authentication, bcrypt hashing, profile updates
- Role-based access: admins see and delete everything, analysts see their own uploads
- Upload validation: extension, magic bytes, size, empty files, corrupted PDFs, password-protected PDFs
- Duplicate detection by SHA-256 content hash, so renaming a file does not defeat it
- Automatic document classification — the user never picks the type
- 7 document types, 80 extractable fields, 28 of them mandatory
- Two-layer validation with 15 arithmetic cross-checks
- Manual review: edit any field, approve, reject with a reason, reprocess
- Dashboard with success rate, average processing time, type and status breakdowns, daily and monthly trends
- Search across filenames and every extracted field; filter by type, status, uploader, date range, processing time
- Export to Excel (multi-sheet), PDF and CSV
- Full audit trail — 19 action types, every stage timed
- Interactive API documentation generated from the code

---

## Local setup

### Prerequisites

Python 3.11+ · Node.js 18+ · a MongoDB Atlas account · a Gemini API key ([free, no card](https://aistudio.google.com/apikey))

### Backend

    cd backend
    python3.12 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python -m scripts.check_setup
    uvicorn app.main:app --reload

`check_setup` tests your Python version, packages, config, MongoDB connection and Gemini key, and names exactly what is wrong. Run it before the server.

API at http://localhost:8000 · docs at http://localhost:8000/docs

### Frontend

    cd frontend
    npm install
    npm run dev

App at http://localhost:5173

The **first account registered becomes the administrator**. Every account after that is an analyst.

---

## Environment variables

### Backend — `backend/.env`

| Variable | Required | Description |
|---|---|---|
| `MONGODB_URL` | yes | Atlas connection string. URL-encode special characters in the password |
| `MONGODB_DB_NAME` | no | Database name. Default `findoc` |
| `SECRET_KEY` | yes | JWT signing key, 48+ random bytes |
| `GEMINI_API_KEY` | yes | From Google AI Studio |
| `GEMINI_MODEL` | no | Default `gemini-3.6-flash`. Configurable because free-tier model availability changes |
| `CORS_ORIGINS` | yes | Comma-separated allowed origins, no trailing slashes |
| `MAX_UPLOAD_SIZE_MB` | no | Default 25 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Default 1440 |
| `DEBUG` | no | Default `false` |

### Frontend — `frontend/.env`

| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend base URL. Only `VITE_`-prefixed variables reach browser code |

---

## Folder structure

    findoc/
    ├── backend/
    │   ├── app/
    │   │   ├── api/           route handlers, one module per resource
    │   │   │   auth.py        register, login, profile
    │   │   │   documents.py   upload, list, search, delete, download
    │   │   │   parser.py      process, result, corrections, approve/reject
    │   │   │   reports.py     report list and Excel/PDF/CSV export
    │   │   │   dashboard.py   aggregation statistics
    │   │   │   logs.py        audit trail
    │   │   ├── core/          config, database, security, dependencies
    │   │   ├── models/        Beanie documents and shared enums
    │   │   ├── schemas/       Pydantic request/response shapes
    │   │   ├── services/      ocr, ai, validation, parser, export, audit
    │   │   ├── parsers/       one declarative spec per document type
    │   │   ├── utils/         file validation and hashing
    │   │   └── main.py
    │   ├── scripts/           setup checker, password reset
    │   ├── tests/             validation engine tests
    │   └── requirements.txt
    ├── frontend/
    │   └── src/
    │       ├── api/           axios instance, interceptors, endpoints
    │       ├── context/       auth state
    │       ├── components/    layout, route guard, shared UI
    │       └── pages/         dashboard, upload, documents, review, reports, logs
    └── docs/
        └── ARCHITECTURE.md    architecture and schema diagrams

### Why the parsers folder is shaped this way

Each document type is described **declaratively** as a `DocumentSpec` — a list of fields with types, descriptions, mandatory flags and validators, plus the arithmetic relationships that should hold between them.

Everything downstream is generated from those specs: the AI prompt, the validation rules, the export columns, and the frontend's review form. Adding an eighth document type means writing one file in `app/parsers/` and adding one line to the registry. No other module changes.

---

## API documentation

Interactive Swagger UI, generated from the code: **https://findoc-api-l3nq.onrender.com/docs**

26 endpoints across six groups.

**Authentication**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create an account. The first one becomes admin |
| POST | `/api/auth/login` | Exchange credentials for a JWT |
| GET | `/api/auth/profile` | Current user |
| PUT | `/api/auth/profile` | Update name or email |
| POST | `/api/auth/logout` | Audited; JWTs are stateless |

**Documents**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/documents/upload` | Upload and queue for parsing |
| GET | `/api/documents` | List with search, filters, pagination |
| GET | `/api/documents/{id}` | One document |
| DELETE | `/api/documents/{id}` | Delete (admin only) |
| GET | `/api/documents/{id}/download` | Original file |

**Parser**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/parser/process/{id}` | Start the pipeline |
| POST | `/api/parser/reprocess/{id}` | Re-run, optionally forcing a type |
| GET | `/api/parser/status/{id}` | Lightweight poll target |
| GET | `/api/parser/result/{id}` | Full result and field definitions |
| PUT | `/api/parser/result/{id}/fields` | Save manual corrections |
| POST | `/api/parser/result/{id}/approve` | Approve extracted data |
| POST | `/api/parser/result/{id}/reject` | Reject with a reason |
| GET | `/api/parser/schema/{document_type}` | Field definitions for a type |

**Reports**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/reports` | List parsed reports |
| GET | `/api/reports/{id}` | One report summary |
| GET | `/api/reports/export/pdf/{id}` | Download PDF |
| GET | `/api/reports/export/excel/{id}` | Download Excel |
| GET | `/api/reports/export/csv/{id}` | Download CSV |

**Dashboard and logs**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard` | Statistics via a single `$facet` aggregation |
| GET | `/api/logs` | Audit entries with filters |
| GET | `/api/logs/document/{id}` | One document's full timeline |

### Supported document types

| Type | Fields | Mandatory | Cross-checks |
|---|---|---|---|
| Bank Statement | 13 | 5 | balance reconciliation, transaction count |
| Salary Slip | 14 | 5 | gross minus deductions equals net, net not above gross |
| Invoice | 12 | 5 | taxable plus tax equals total, tax plausibility |
| ITR | 11 | 3 | gross minus deductions equals taxable income |
| GST Return | 11 | 5 | CGST plus SGST plus IGST equals total, CGST equals SGST |
| Profit & Loss | 11 | 2 | revenue minus COGS equals gross profit |
| Balance Sheet | 8 | 3 | assets equal liabilities plus equity |

---

## Testing

    cd backend
    source venv/bin/activate
    python -m tests.test_validation

23 assertions covering the GSTIN checksum, PAN entity codes, IFSC format, currency coercion (`Rs. 45,000/-` becomes `45000`, brackets mean negative, lakh grouping), day-first date parsing, and every category of cross-field check.

No database and no API calls, so the suite runs offline in under a second.

---

## Deployment

### Backend — Render

`backend/render.yaml` defines the service. Connect the repository, set root directory to `backend`, and supply `MONGODB_URL`, `GEMINI_API_KEY` and `CORS_ORIGINS` as environment variables.

Build command: `pip install -r requirements.txt`
Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

`backend/.python-version` pins Python 3.12 — several dependencies have no prebuilt wheels for 3.13 yet.

### Frontend — Vercel

Import the repository, set **Root Directory** to `frontend`, framework preset Vite, and set `VITE_API_URL` to the Render URL.

`frontend/vercel.json` rewrites all paths to `index.html` so React Router handles deep links — without it, refreshing on `/documents/abc123` returns 404.

### Database — MongoDB Atlas

M0 free tier, Mumbai region. Network access must allow `0.0.0.0/0` because Render assigns a different egress IP on each deploy.

### Why the backend is not also on Vercel

Vercel runs serverless functions that terminate once a response is returned. Parsing takes 10 to 20 seconds and runs in a background task *after* the 201 is sent, so the process would be killed mid-parse. Render runs a persistent server, which this workload requires.

---

## Assumptions

- Documents are Indian financial documents. Validation encodes Indian rules — PAN structure, GSTIN checksums and state codes, IFSC format, day-first dates, lakh and crore number grouping.
- Dates are day-first. `03/04/2024` is 3 April, not 4 March.
- The first registered account is the administrator. A fresh deployment otherwise has no way to create one.
- Uploads are single documents, not multi-document bundles.
- Amounts are in INR unless the document states otherwise.
- One parsed report per document; reprocessing overwrites it rather than versioning.
- Masked account numbers are kept exactly as printed rather than rejected.

---

## Known limitations

**Uploaded files do not survive a restart.** Render's filesystem is ephemeral. Parsed data lives in MongoDB and is unaffected, but re-downloading an original file after a restart returns 410. Object storage is the fix.

**No self-service password reset.** A real one needs email delivery and single-use expiring tokens. Recovery is via `scripts/reset_password.py`, which requires shell access to the server.

**JWTs cannot be revoked before expiry.** Logout discards the token client-side and is audited, but a stolen token stays valid until it expires. Proper revocation needs a Redis blocklist checked on every request.

**Background tasks are in-process.** FastAPI's `BackgroundTasks` runs parsing in the same process, so a restart mid-parse loses that job — the document stays on `processing` until reprocessed. Celery with Redis would fix this but needs a separate worker, which free-tier Render does not provide.

**Free-tier rate limits.** Gemini's free tier limits requests per minute. The service retries with exponential backoff, but a burst upload can still exhaust the quota.

**No admin user-management UI.** Roles are assigned by the server. Promoting an analyst currently requires a database update.

**Extraction accuracy is not benchmarked.** There is no labelled test set measuring field-level accuracy across real document formats. `parsed_data` is kept separate from `corrected_data` specifically so this could be measured later from reviewer corrections.

**Cold starts.** Render's free tier sleeps after 15 minutes; the first request takes about 50 seconds.

---

## Future improvements

- Object storage for uploaded files, removing the ephemeral filesystem problem
- Celery and Redis for durable background processing and true queue semantics
- WebSocket progress updates instead of client polling
- Per-field confidence scores rather than one score per document
- Batch upload and bulk approval
- Accuracy benchmarking harness built from accumulated reviewer corrections
- Transaction categorisation and fraud signals on bank statements
- Multi-tenant organisations with per-tenant data isolation
- Email ingestion — parse documents arriving as attachments
- Docker Compose for one-command local setup

---

## Author

**Priyanshu Tiwari**

Repository: https://github.com/Tiwari-Priyanshu/financial-document-parser