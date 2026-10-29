# Product Audit — "My Chatbot" (cpbot) Supplier Finance SaaS

Audited: FastAPI (`main.py`, 2207 lines, monolithic) + Angular 22 frontend + PostgreSQL (asyncpg) + Claude (chat/OCR) + Gemini (embeddings/TTS). Read-only investigation, no code changed. Every claim below is sourced to a specific file:line; anything not directly verified is marked 🔍.

## 1. Executive Summary

The product is a working, multi-tenant RAG chatbot with a real admin dashboard, an Odoo-linked variant, FAQ management, and a production-grade embeddable widget (signed JWT SSO, locked-down CORS, role capped to "member"). The RAG pipeline itself is above-average for a first build: a genuinely good system prompt (explicit anti-hallucination, source-integrity, and completeness rules), real Postgres Row-Level Security policies (not just app-code filtering), consistent parameterized SQL, and zero IDOR findings across ~20 audited endpoints.

**What's already good**: widget SSO security, prompt design, consistent tenant filtering, password hashing (bcrypt), CORS allow-list (not wildcard), OCR fallback for scanned documents via Claude Vision, existing unit tests for two routers.

**Biggest weaknesses**: (1) the RLS layer is almost certainly neutered in production because the app connects to Postgres as the `postgres` role, which on RDS carries `rds_superuser` and bypasses RLS regardless of `FORCE ROW LEVEL SECURITY` — the DB-level backstop likely does nothing today, leaving isolation resting entirely on the (correctly-written, but unverified-by-RLS) app code; (2) document upload is fully synchronous — a large PDF blocks the HTTP request through OCR and per-chunk embedding calls; (3) no rate limiting anywhere, including `/login`; (4) the JWT `SECRET_KEY` is a hardcoded placeholder string committed in `core/config.py`, not sourced from env; (5) several `/admin`-prefixed endpoints check tenant membership but never check role server-side, relying on the frontend to hide the button.

**Biggest risks for selling this**: there is no self-service signup (tenants are superadmin-created only), no billing/subscription scaffolding, no lead capture, no human handoff, and no notification system — the product today is an internal tool successfully running for 1-2 known tenants (Credit Plus, Housing Bank), not yet a self-serve SaaS.

**Overall readiness: the system works and is reasonably secure for a single/few hand-onboarded enterprise clients today; it is not yet ready to be sold as self-serve SaaS.**

| Area | Score |
|---|---|
| Product readiness (overall) | **52/100** |
| Frontend | 65/100 |
| Backend | 62/100 |
| AI/RAG | 58/100 |
| Security | 50/100 |
| UX | 55/100 |
| SaaS architecture | 40/100 |
| Commercial readiness | 28/100 |

## 2. Existing Features

| Feature | Status | Evidence | Problems | Recommendation |
|---|---|---|---|---|
| Login/logout, bcrypt hashing | ✅ | `core/security.py:10-26`, `main.py:223-262` | None found | — |
| Password reset / forgot password | ❌ | repo-wide grep, zero matches | New customers locked out need manual DB fix | Add before external users exist |
| JWT auth, httpOnly cookie | ✅ | `core/security.py:49-56` (`secure=True, samesite=none`) | Odoo-SSO/widget flows return raw token in JSON body by design (server-to-server), fine | — |
| Refresh tokens | ❌ | grep "refresh_token", zero matches | Hard logout every 30 min, no silent renewal | Low priority if session UX is acceptable |
| Role-based guards (admin/member/superadmin) — frontend | ✅ | `frontend/.../guards/*.ts`, now async + server-verified (this session's fix) | — | — |
| Role-based guards — backend | ⚠️ | `main.py:1265,1291,1154,407,1529,1793` etc. have tenant check but **no role check** | Non-admin member can call admin-only actions via direct API call | Add `require_admin`/`require_role` dependency to every admin-prefixed/admin-intent route |
| Multi-tenant isolation (app-level) | ✅ | ~20 endpoints audited, all `WHERE id=$1 AND tenant_id=$2` | None found | — |
| Multi-tenant isolation (DB-level RLS) | ⚠️ | Real policies exist (`backup.sql:1472-1596`) but app connects as `postgres`/`rds_superuser`, which bypasses RLS | DB backstop is very likely inert; isolation rests solely on app code | Create a least-privilege app DB role without BYPASSRLS, update `DATABASE_URL` |
| Document upload: PDF/DOCX/XLSX/TXT/PPTX/PPT | ✅ | `services/extraction.py`, `main.py:415-420` | No CSV, no file-size limit, no magic-byte validation | Add size cap + content-sniffing |
| OCR for scanned PDFs/PPTX images | ✅ | `extraction.py:70-99,164-193` via Claude Vision | Synchronous, slow for large files | Move to background job |
| Document processing status | ⚠️ | `processing`→`ready` tracked but flips synchronously inside the same request | No real async state, request blocks for full OCR+embed duration | Background worker/queue |
| RAG retrieval + relevance gating | ✅ | `services/search.py`, `main.py:693,944-958` | No reranker, naive fixed-size chunking (`chunking.py:1`, 800/100 chars) | Consider chunk-size tuning, optional reranker |
| Conversation memory | ✅ | `main.py:1064-1073`, last 6 messages | No summarization of older turns | Fine for now |
| Source citations (computed) | ⚠️ | `main.py:1107` returns raw chunk previews | **Frontend never renders them** (`chat-page.html` has no `sources`/`slide_source` binding) | Wire citations into the chat UI — cheap, high-trust win |
| Feedback (👍/👎) | ✅ | `POST /rate`, `main.py:1132-1150` | No aggregated-ratings GET endpoint found | Add an admin view of ratings |
| AI usage monitoring | ✅ | `ai_predictions_log` + superadmin dashboard with real SVG chart (`ai-monitoring.ts`) | Latency/success only — **no token count or $ cost tracked** | Add cost tracking, surface to tenant admins too (today superadmin-only) |
| Embeddable widget (SSO, CORS, branding) | ✅ | `routers/widget.py` (full file reviewed) | None found — well-built | — |
| FAQ management (admin + member view) | ✅ | `routers/faq_categories.py`, tested (`tests/test_faq_categories.py`, 481 lines) | — | — |
| Odoo integration (SSO, agent, dashboard) | ✅ | `services/odoo_service.py`, `services/odoo_agent.py` | 🔍 not deeply audited this pass | — |
| Rate limiting | ❌ | grep "slowapi\|Limiter\|rate_limit", zero hits | `/login`, `/register`, `/ask` all unthrottled | Add slowapi or similar before public exposure |
| Lead capture | ❌ | grep "lead" repo-wide, no real hits | No way to monetize anonymous widget visitors | P0 for a sales-facing chatbot product |
| Human handoff / escalation | ❌ | grep "handoff\|escalat\|ticket\|human agent", zero matches | AI-only, no fallback when it can't answer | P1 |
| Email notifications | ❌ | grep "notif", zero matches; no smtplib/sendgrid/ses dependency | No alert on failed processing, no lead email, etc. | P1 |
| Billing/subscription/plans | ❌ | grep "stripe\|billing\|subscription\|plan", no real hits | Cannot charge customers or gate usage by tier | P0 before commercial launch |
| Self-service tenant signup | ❌ | `/register` only adds a user to an **existing** tenant (`main.py:155-170`); new tenants only via superadmin `POST /admin/tenants` | Onboarding is fully manual today | P0 for self-serve SaaS motion |
| CI/CD | ❌ | no `.github/workflows`, no Dockerfile/docker-compose anywhere in repo | Deployment is manual IIS/Windows (`deploy/README-DEPLOY.md`) | Containerize + add CI before scaling team/customers |
| Automated tests | ⚠️ | 2 test files, 667 lines, cover `faq_categories` + `widget_sso` only | ~60 endpoints, 2 tested | Expand coverage, especially auth/RAG/tenant-isolation paths |

## 3. Missing Features (prioritized)

**P0 — Critical before selling**
1. Self-service tenant signup/onboarding flow
2. Billing/subscription infrastructure (even just Stripe Checkout + a `plans`/`tenant_plan` table)
3. Rate limiting on `/login`, `/register`, `/ask`
4. Fix the DB role so RLS actually applies (least-privilege app role, no BYPASSRLS/rds_superuser)
5. Replace hardcoded `SECRET_KEY` with a required env var, generate a real random value
6. File size limits on uploads (`/documents/upload`, `/media/upload`)

**P1 — Important for first real customers**
7. Lead capture (name/email/phone during widget chat, leads table, admin leads view)
8. Human handoff / "talk to a person" escalation
9. Email notifications (new lead, processing failure, system error)
10. Server-side role checks on every admin-intent endpoint (not just tenant checks)
11. Wire source citations into the chat UI (already computed server-side, just not rendered)
12. Password reset flow
13. Background job queue for document processing (don't block the upload request)
14. Per-tenant (not just superadmin) usage/analytics visibility

**P2 — Valuable later**
15. Token/cost tracking alongside the existing latency monitoring
16. Reranking step in RAG retrieval
17. CSV upload support
18. Expanded automated test coverage (auth, tenant isolation, RAG)
19. Refresh tokens / silent session renewal
20. Containerized deployment + CI pipeline

**P3 — Nice to have**
21. White-label branding beyond the widget (full admin-dashboard theming)
22. Webhooks / public API access for integrations
23. Conversation export, advanced analytics (cohort/retention)

## 4. Bugs / Problems

| Problem | Location | Why it matters | Severity | Fix |
|---|---|---|---|---|
| App DB connection likely bypasses RLS | `db.py:8` (`DATABASE_URL`), `.env` role `postgres` | DB-level tenant isolation backstop is probably inert; a bug in app-code filtering would leak cross-tenant data with no safety net | High | Create least-privilege Postgres role without BYPASSRLS/superuser for the app |
| Hardcoded JWT secret placeholder | `core/config.py:1` | If deployed with the placeholder, all sessions are forgeable | High | Require `SECRET_KEY` from env, fail startup if unset/default |
| No role check on several admin-intent endpoints | `main.py:1265,1291,1338,1154,407,1529,1793` (see list in §2) | Any authenticated member can call these via direct API request, bypassing the frontend's guard-based UI hiding | High | Add `require_admin` dependency |
| Synchronous document processing | `main.py:446-468,510-538,558-582` | Large file uploads block the HTTP request for the full OCR+embedding duration; risk of timeouts and poor UX at scale | Medium | Background worker (Celery/RQ/async task) |
| No file size limit on uploads | `main.py:407-609`, `1154-1210` | Unbounded `file.read()` — DoS risk via huge uploads | Medium | Enforce `Content-Length`/stream-limit |
| No rate limiting anywhere | repo-wide | Brute-force on `/login`, cost abuse on `/ask` | Medium-High | Add slowapi or API-gateway-level limiting |
| `faq_items`/`error_solutions` tables have no RLS | `migrations/006,007` comments | Relies purely on app-code filtering (which was verified correct, but it's the only line of defense) | Low-Medium | Add RLS for defense-in-depth consistency |
| Stale doc comment in `.env.example` | `.env.example:18-19` | Claims Postgres DSN is hardcoded in `db.py`; it's actually read from env (`db.py:8`) | Cosmetic | Update comment |
| Raw string-built SQL in offline script | `scripts/backfill_translations.py:60,81` | Not user-facing (developer-run migration script), but still a bad pattern if ever adapted | Low | Parameterize or restrict to a fixed column allow-list |
| No aggregated ratings view | — (only `POST /rate` found) | 👍/👎 feedback is collected but never surfaced to admins | Low | Add a `GET /ratings/summary` + admin view |

## 5. Security Risks

- **RLS likely bypassed in production** (see §4) — the single biggest structural security risk; everything currently rests on app-code `WHERE tenant_id = $N` discipline, which was verified correct today but has no DB-level enforcement if a future query forgets the filter.
- **Hardcoded SECRET_KEY placeholder** committed in source (`core/config.py:1`).
- **No rate limiting** on `/login` (credential stuffing/brute force) or `/ask` (cost-abuse / scraping).
- **No role check on backend** for several admin-intent endpoints — defense relies on the frontend only.
- **No file size limits** on document/media upload endpoints.
- **No magic-byte validation** on uploaded files — only filename extension is checked; a malicious file with a spoofed extension would be processed by the extraction pipeline.
- **No prompt-injection mitigation**: retrieved document text is concatenated directly into the system prompt with no delimiters and no explicit "ignore instructions found inside documents" rule — a malicious/compromised document could attempt to steer the model's behavior for that tenant's users.
- CORS, SQL parameterization, password hashing, widget JWT handling (algorithm pinning, audience/exp enforcement, short TTL cap) were all checked and found solid — no issues found there.

## 6. UX Problems

- Source citations are computed by the backend but never shown in the chat UI — a missed trust-building opportunity with near-zero implementation cost.
- No visible toast/notification UI component in `frontend/src/app/shared/` — unclear how transient errors/success states surface to the user outside inline messages (🔍 not fully verified this pass).
- Analytics dashboard exists but is superadmin-only; tenant admins — the actual paying customers in a multi-tenant SaaS — cannot see their own usage.
- No password-reset self-service flow means any locked-out user needs manual intervention.
- Large document uploads block the UI for the full processing duration with no background/async feedback loop beyond a spinner (implied by synchronous processing finding).

## 7. Commercial Gaps

What currently prevents this from being a sellable, self-serve SaaS:
1. **No self-service signup** — every tenant is onboarded manually by a superadmin via `POST /admin/tenants`. There is no "create your company account" flow a prospective customer could use unassisted.
2. **No billing** — no Stripe or any payment integration, no plan/tier model, no usage-based or seat-based limits enforced anywhere.
3. **No lead capture or human handoff** — for a product whose main pitch to a *company* is "convert your website visitors," the actual lead-generation loop doesn't exist yet.
4. **No notification system** — customers have no way to be alerted to processing failures, new leads, or anomalies without checking the dashboard.
5. Usage/cost visibility is superadmin-only, not tenant-facing — a paying customer can't see what they're using or being billed for.

The underlying architecture (tenant-scoped tables, per-tenant JWT claims, tenant-aware RAG retrieval, widget SSO keyed by tenant slug) is **subscription-ready in shape** — it's a missing billing/plan layer and a missing self-serve onboarding flow, not a fundamental redesign, that stand between here and sellable SaaS.

## 8. Recommended Product

A multi-tenant AI knowledge assistant where: a company signs up itself, uploads its docs, gets an embeddable widget and an admin dashboard with its own usage/cost view, the chatbot captures leads and can hand off to a human when unsure, admins get email alerts, and the whole thing is billed on a plan (e.g. message-volume or seat-based tiers) via Stripe. The AI/RAG core already largely supports this; the gaps are in the business/operational layer wrapped around it.

## 9. Recommended Architecture

Keep: FastAPI + asyncpg + Postgres w/ pgvector, Claude for generation/OCR, Gemini for embeddings/TTS, Angular 22 frontend, the existing widget SSO pattern, and the RLS table design (just fix the connecting role).

Add:
- A background job runner (even a simple `asyncio`-based queue, or RQ/Celery if scale demands) for document processing, decoupled from the upload request.
- A `plans`/`subscriptions` table + Stripe webhooks, gated via a dependency similar to the existing `require_admin`/`require_superadmin` pattern.
- A `leads` table + widget-side capture UI + admin leads dashboard.
- A least-privilege Postgres role for the app (no BYPASSRLS), with `postgres`/superuser reserved for migrations only.
- A rate-limiting middleware (slowapi) in front of `/login`, `/register`, `/ask`.
- An email-sending service (SES/SendGrid) wired into processing-failure and new-lead events.
- Minimal CI (lint + the existing 2 test files, expanded) and a Dockerfile, even if production stays on IIS for now — mainly for reproducible local dev and future portability.

## 10. Roadmap

### Phase 1 — Must Fix
- Least-privilege DB role (stop relying on a bypassed RLS)
- Real `SECRET_KEY` from env, fail-fast if missing/default
- Rate limiting on auth + `/ask`
- Server-side role checks on all admin-intent endpoints
- File size limits on uploads

### Phase 2 — Core SaaS Features
- Self-service tenant signup
- Password reset flow
- Background job queue for document processing
- Tenant-facing usage/analytics view
- Wire citations into the chat UI

### Phase 3 — Commercial Features
- Billing/subscription (Stripe) + plan-gated limits
- Lead capture (widget + admin dashboard)
- Email notifications

### Phase 4 — Advanced AI
- Token/cost tracking per call
- Optional reranking step
- Human handoff / escalation flow

### Phase 5 — Scale
- Containerization + CI/CD
- Expanded automated test coverage
- Webhooks / public API for integrations
- White-label branding beyond the widget
