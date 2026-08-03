# Architecture

## System overview

```mermaid
graph TB
    subgraph client["Browser"]
        UI["React 19 + Vite<br/>Tailwind 4"]
    end

    subgraph vercel["Vercel"]
        STATIC["Static bundle<br/>SPA rewrites"]
    end

    subgraph render["Render — FastAPI"]
        API["API layer<br/>auth · documents · parser<br/>reports · dashboard · logs"]
        DEPS["Dependencies<br/>JWT verify · RBAC"]
        SVC["Services<br/>ocr · ai · validation<br/>parser · export · audit"]
        SPEC["Parser specs<br/>7 declarative DocumentSpecs"]
        BG["Background tasks<br/>asyncio.to_thread"]
    end

    subgraph external["External"]
        MONGO[("MongoDB Atlas<br/>Mumbai · M0")]
        GEMINI["Google Gemini<br/>3.6 Flash"]
    end

    DISK["Local disk<br/>uploads/ (ephemeral)"]

    UI -->|"axios + Bearer JWT"| STATIC
    STATIC -.->|"HTTPS / CORS allowlist"| API
    API --> DEPS
    DEPS --> SVC
    SVC --> SPEC
    API --> BG
    BG --> SVC
    SVC --> MONGO
    SVC -->|"only when no text layer"| GEMINI
    SVC --> DISK
```

## Processing pipeline

The decision that shapes the whole system is at the OCR step: most Indian
financial PDFs are digitally generated and already carry a text layer. Reading
that directly is faster, free, and more accurate than sending pixels to a
vision model. The model is the fallback, not the default.

```mermaid
flowchart TD
    A["POST /api/documents/upload"] --> B{"Validation<br/>extension · magic bytes · size<br/>encryption · corruption"}
    B -->|fails| B1["400 with reason code"]
    B -->|passes| C{"SHA-256 already seen<br/>for this user?"}
    C -->|yes| C1["409 duplicate<br/>+ existing document id"]
    C -->|no| D["Store on disk with UUID name<br/>Insert Document record"]
    D --> E["201 returned immediately"]
    D --> F["Background task starts"]

    F --> G{"PDF with<br/>text layer > 200 chars?"}
    G -->|yes| H["pdfplumber<br/>~50ms · no API call"]
    G -->|no| I["Gemini vision OCR<br/>~5s · 1 API call"]

    H --> J["Classify document type"]
    I --> J
    J --> K{"Confidence >= 0.55?"}
    K -->|no| L["UNKNOWN → human decides type"]
    K -->|yes| M["Extract fields against the type's spec"]

    M --> N["Normalise<br/>Rs. 45,000/- → 45000<br/>17/09/2024 → 2024-09-17"]
    N --> O["Validate: format layer<br/>PAN · GSTIN checksum · IFSC · dates"]
    O --> P["Validate: arithmetic layer<br/>15 cross-field checks"]

    P --> Q{"Mandatory field<br/>missing or malformed?"}
    Q -->|yes| R["VALIDATION_FAILED"]
    Q -->|no| S["REVIEW_PENDING"]

    S --> T["Analyst edits · approves · rejects"]
    R --> T
    L --> T
    T --> U["Export: Excel · PDF · CSV"]
```

Every stage writes an audit entry, so `GET /api/logs/document/{id}` returns the
document's full timeline with per-stage timings.

## Database schema

Four collections. MongoDB has no foreign keys, so the relationships below are
enforced in application code — a deliberate trade documented under Known
Limitations in the README.

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : uploads
    DOCUMENTS ||--|| PARSED_REPORTS : "has one"
    DOCUMENTS ||--o{ AUDIT_LOGS : "generates"
    USERS ||--o{ AUDIT_LOGS : performs
    USERS ||--o{ PARSED_REPORTS : reviews

    USERS {
        ObjectId _id PK
        string name
        string email UK "unique index"
        string password_hash "bcrypt, cost 12"
        enum role "admin | analyst"
        bool is_active
        datetime created_at
        datetime updated_at
    }

    DOCUMENTS {
        ObjectId _id PK
        string document_name
        enum document_type "null until classified"
        string file_path
        int file_size
        string mime_type
        string file_hash "SHA-256, duplicate detection"
        string uploaded_by FK
        string uploader_name "denormalised"
        string uploader_email "denormalised"
        enum status "7 processing states"
        float processing_time
        string error_message
        datetime created_at
        datetime updated_at
    }

    PARSED_REPORTS {
        ObjectId _id PK
        string document_id FK "unique index"
        string raw_text "OCR output, capped 100KB"
        object parsed_data "AI output, never overwritten"
        object corrected_data "manual edits, wins on export"
        enum validation_status "passed | partial | failed"
        array validation_errors
        enum review_status
        string reviewed_by FK
        string reviewer_name
        string remarks
        float confidence_score
        string extraction_method "native_text | gemini_vision"
        datetime created_at
        datetime updated_at
    }

    AUDIT_LOGS {
        ObjectId _id PK
        string document_id FK "nullable"
        string document_name
        string user_id FK "nullable"
        string user_name
        enum action "19 action types"
        enum status "success | failure | info"
        string remarks
        float processing_time
        datetime created_at
    }
```

### Indexes and why each exists

| Collection | Index | Reason |
|---|---|---|
| `users` | `email` (unique) | Prevents duplicate accounts under concurrent registration — an application-level check has a race window |
| `documents` | `uploaded_by + file_hash` | Duplicate detection is always scoped per user, so one compound index serves the lookup |
| `documents` | `status + created_at` | The document list filters by status and sorts newest-first — the hot path |
| `documents` | `document_name` (text) | Filename search |
| `parsed_reports` | `document_id` (unique) | Enforces one report per document |
| `parsed_reports` | `parsed_data.$**` (wildcard) | Indexes every extracted field at any depth, so PAN, GSTIN, invoice number, account number and names are all searchable without an index per field |
| `audit_logs` | `document_id`, `created_at` | Timeline reconstruction per document |

### Schema decisions worth explaining

**`parsed_data` as a JSON object, not columns.** The seven document types share
almost no fields — a bank statement has an IFSC code, a salary slip has a PF
deduction. A relational table would be roughly 60 columns that are 85% NULL.

**`corrected_data` stored separately from `parsed_data`.** When a reviewer fixes
a value, the model's original output survives. Overwriting it would make
"how accurate is our extraction?" permanently unanswerable.

**Reports split from documents rather than embedded.** The pure-Mongo instinct
is to embed, but a bank statement's transaction list plus raw OCR text can
exceed 100 KB. The document list endpoint is the most-hit route and needs none
of it, so embedding would drag that payload into every page of results.

**Uploader name and email denormalised onto documents.** This is the extended
reference pattern: the list view shows who uploaded each file without a lookup
per row. The trade is that renaming a user leaves historical documents showing
the old name — arguably correct for an audit trail.
