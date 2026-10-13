# Pact Core 🤝

> **Autonomous, AI-Arbitrated Escrow Protocol for Digital Deliverables.**

![Pact Architecture](arch.png)

Pact eliminates the two-sided trust dilemma in digital transactions. Traditional escrow requires slow, expensive, and subjective human dispute mediators ($20–$50/ticket, taking days). Pact replaces human arbitration with a deterministic quality gate and a fast Groq LLM judge — holding buyer funds via PayPal's two-phase authorization and autonomously settling payments in seconds.

---

## 💡 The Core Problem

In freelance data sourcing and digital deliverable markets (e.g. AI training datasets, data labeling, fine-tuning records):
1. **The Buyer's Risk**: If buyers pay upfront, sellers may deliver garbage, corrupted mock data, or malicious adversarial payloads (e.g., prompt injections).
2. **The Seller's Risk**: If sellers deliver first, buyers can take the dataset, refuse release, or demand endless unpaid revisions.
3. **The Escrow Friction**: Traditional platforms give either the buyer all the leverage (Upwork milestones) or charge high arbitration fees (Escrow.com).

**Pact's Solution**: Zero human intervention. Funds are frozen on PayPal upfront, the seller submits the deliverable, an AI agent validates the work against strict criteria, and payments are automatically captured or refunded based on the AI's verdict.

---

## ⚡ How It Works (The Lifecycle)

```
[Buyer Dashboard]               [Django + Celery Engine]            [Groq LLM & PayPal]
       │                                   │                                  │
       ├── 1. Create Contract ($150) ─────►│                                  │
       │                                   ├── 2. Create PayPal Order ───────►│ (intent: AUTHORIZE)
       ├── 3. Approve via PayPal Modal ───►│                                  │
       │   (Funds frozen on buyer card)    │── 4. State: AUTHORIZED           │
       │                                   │                                  │
[Seller Portal]                            │                                  │
       │                                   │                                  │
       ├── 5. Submit JSON Dataset ────────►│                                  │
       │                                   ├── 6. State: SUBMITTED            │
       │                                   ├── 7. Enqueue Celery Task         │
       │                                   │                                  │
       │                                   │── 8. Gate 1: Deterministic Check │ (list, >= 2 dicts)
       │                                   │      [FAIL] ──► Void Hold & Reject
       │                                   │                                  │
       │                                   │── 9. Gate 2: Groq Semantic Audit │
       │                                   │      (Checks injection & quality)│
       │                                   │                                  │
       │                                   │── 10. Settlement Decision:       │
       │                                   │       - Passed AND Conf >= 85%:  │
       │                                   │         Capture Hold ───────────►│ (Seller paid)
       │                                   │       - Failed OR Conf < 85%:    │
       │                                   │         Void Hold ──────────────►│ (Buyer refunded)
       ▼                                   ▼                                  ▼
                            [Live Audit Ledger (Polling 3s)]
```

---

## 🛡️ Key Architectural & Product Decisions

### 1. Two-Phase Programmable Escrow (PayPal v2 REST)
Unlike standard e-commerce carts with instant capture (`intent: capture`), Pact uses **`intent: authorize`**. Funds are frozen on the buyer's payment instrument without transferring to the platform or seller. When verification resolves, the backend programmatically captures (`capture_authorization`) or voids (`void_authorization`) the hold with zero platform dispute overhead.

### 2. Two-Tiered Verification Pipeline
- **Gate 1: Deterministic Quality & Structure (`escrow/tasks.py`)**
  Runs before invoking LLM inference (zero-cost filtering). Ensures the payload is a valid list of at least 2 dictionary items. Fails instantly to `REJECTED` if malformed.
- **Gate 2: Adversarial & Semantic Analysis (`escrow/services/ai_service.py`)**
  Evaluated using Groq (`llama3-70b-8192` / LPU inference) with structured JSON output enforced via Pydantic:
  - **Prompt Injection Defense**: Detects jailbreaks and hidden instructions (e.g., `"IGNORE INSTRUCTIONS"`, `"CONFIRM PAYMENT"`).
  - **Data Quality**: Flags empty fields, gibberish strings, low-effort filler, and corrupted records.

### 3. The 85% Confidence Floor
Even if the AI reports `passed: true`, if `confidence_score < 0.85`, the platform **fails safe** and voids the hold back to the buyer. This deliberate bias guarantees that real money is never paid out on ambiguous or unverified deliverables.

### 4. Immutable Append-Only Ledger (`PactLedger`)
Every lifecycle event (`PACT_CREATED`, `AUTHORIZED`, `DELIVERABLE_SUBMITTED`, `REVIEW_STARTED`, `FUNDS_CAPTURED`, `FUNDS_VOIDED`) is recorded in a tamper-proof audit log. Updates and deletions are prevented at the model level (`ValidationError` on update/delete).

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, Django 5.1, Django REST Framework, Celery, Redis, PostgreSQL
- **AI Verification**: Groq SDK (`llama3-70b-8192`), Pydantic v2
- **Payment Gateway**: PayPal REST API v2 (Two-phase Authorization & Webhook Cryptographic Verification)
- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS v4, `@paypal/react-paypal-js`, Axios

---

## 🚀 Getting Started

### 1. Backend Setup (`pact_core`)

```bash
cd pact_core

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and supply your credentials:
# - PAYPAL_CLIENT_ID & PAYPAL_CLIENT_SECRET
# - GROQ_API_KEY
# - DB credentials & CELERY_BROKER_URL

# Run migrations
python manage.py migrate

# Start Redis & Celery Worker
celery -A pact_core worker -l info

# Start Django Development Server
python manage.py runserver 127.0.0.1:8000
```

### 2. Frontend Setup (`pact-frontend`)

```bash
cd ../pact-frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env.local
# Set NEXT_PUBLIC_PAYPAL_CLIENT_ID and API endpoint

# Start Next.js Development Server
npm run dev
```

Visit **`http://localhost:3000`** in your browser:
1. **Buyer Dashboard (`/`)**: Input an escrow amount and authorize via PayPal.
2. **Seller Portal (`/seller`)**: Paste your JSON dataset payload and submit for verification.
3. **Live Ledger (`/ledger`)**: Track real-time polling updates, Groq confidence scores, and state transitions.

---

## 🧪 Running Tests

```bash
cd pact_core
python manage.py test escrow.tests
```

The test suite covers:
- Unit tests for PayPal API token caching and webhook cryptographic signature verification.
- Groq AI service verification schema validation and injection rejection.
- Celery task deterministic gates, resolution logic, and state machine transitions.

---

