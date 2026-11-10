# Fix vitabot's locks before granting write powers

Yes, vitabot should answer permission questions and, later, carry out Odoo write requests such as "allow Ahmed on the Riyadh branch". There is one condition: **Odoo must execute the write as the requesting user, never as the bot's service account, and only after the user confirms a server-side proposal with a button the model cannot forge.** Today the Ask Odoo agent sends every call through a single privileged XML-RPC service account (`services/odoo_service.py:31-80`). It knows the requester only as an email string in the prompt (`services/odoo_agent.py:461-474`). So Odoo's own permission checks currently evaluate the bot, not the person. This is the "shared high-privilege account" pattern OWASP lists as Excessive Agency ([OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)).

Odoo already enforces the core rule: only "Access Rights" users (`base.group_erp_manager`) can write `res.users` ([ir.model.access.csv 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/ir.model.access.csv)). But **Odoo has no check that stops such an admin from granting a company they do not hold themselves**, so vitabot's addon needs exactly one custom policy on top. Before any of this, vitabot's own authorization has holes that would turn write actions into an escalation path. Any authenticated member can bulk-create admins through `/users/import/confirm`, SSO tokens last ten years, a 365-day admin-token generator sits in the repo, and `/odoo/ask` has no rate limit and trusts chat history sent by the client.

The recommended path has four steps. First close those holes. Then ship read-only "who can access what / can I do X" answers evaluated *as the requester*. Then add propose-only previews. Finally add confirmed single-branch writes through a new `cpbot_vita_bot_link` endpoint, with two-person approval reserved for security-group changes. Two caveats apply. The Odoo source research covered versions 16–19, while the addon targets **Odoo 15** (`cpbot_vita_bot_link/__manifest__.py:3`, version `15.0.1.0.9`), so the Odoo 15 details below must be verified. And "branch" still has to be pinned down as company or warehouse.

## Ask Odoo already has the scaffolding for writes, but the wrong identity

The product is stronger as a knowledge-base and support bot than as an ERP copilot. It has:

- multi-tenant bilingual RAG over pgvector, with media, slides, TTS and STT;
- FAQ management;
- support-ticket handoff;
- tenant analytics (top questions, weak answers, satisfaction);
- superadmin AI monitoring;
- an SSO widget.

These live in `main.py` (about 3,100 lines and 70 routes) plus seven routers. The Odoo side is partly switched off. The member-facing "Ask Odoo" page redirects to chat (`frontend/src/app/app.routes.ts:218-227`). The backend `/odoo/ask` route is still live for the superadmin `odoo-chat` page and for the Odoo-embedded `cpbot_vita_insights` widget.

The useful news is that **the Ask Odoo agent is already the right shape for a write layer.** It is a Claude (`claude-sonnet-5`) tool loop with a `TOOLS` schema list, a `_TOOL_FUNCTIONS` dispatch map and up to four rounds (`services/odoo_agent.py:159-416, 419-575`). The application, not the model, executes each tool call. It also already has a side-channel pattern: `present_chart` captures its arguments into a payload instead of calling Odoo (`services/odoo_agent.py:543-551`). A `propose_*` tool can return a pending action the same way, and `/odoo/ask` would pass an extra `pending_action` key through next to `chart` (`main.py:3051`).

The problem is identity. Every Odoo call authenticates as one account: either the environment's `ODOO_USERNAME`/`ODOO_PASSWORD`, or a per-client row in `odoo_client_connections` (`services/odoo_service.py:532-568`). The Odoo SSO addon sends only `email`, `username`, `odoo_user_id`, `client_key` and `company_slug` (`cpbot_vita_bot_link/controllers/sso.py:286-292`). The backend then provisions a plain `member`. **No Odoo groups and no allowed companies cross the boundary.** The SSO token does not even carry `company_id` or the Odoo uid (`main.py:786-796`).

The one durable link to the person's Odoo identity is `users.odoo_identity`, stored as `"{client_key|internal}:{odoo_user_id}"` (`main.py:695, 727, 759-763`). That is enough to recover the requester's Odoo uid on the server without changing the SSO protocol. It is also far more reliable than the email match Ask Odoo uses today.

The read-only permission feature already shows why identity matters. `get_user_access_rights(name)` resolves the target with `ilike` and `limit: 1`. On a miss it returns **every system username** to the LLM (`services/odoo_service.py:431-471`). It runs as the service account behind `/odoo/ask`, and the only gate on that route is `require_vita_care_tenant`. So **any Vita Care member can ask about any colleague's access rights today**, and a vague name can resolve to the wrong person. "Can I do X?" is answered by the LLM reasoning over group names (`services/odoo_agent.py:113-121`), not by an Odoo ACL check. That is tolerable for casual Q&A but unusable as a basis for authorizing a write.

The market has moved the baseline. Odoo 20's native agents now create and update records with a preview and confirmation. Users answer permission requests with buttons, and the agent pauses for confirmation once it hits a tool-call limit ([Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)). Third-party apps such as Claudoo market that they "always run as the logged-in user, never as superuser", with per-user read/write/act permissions and a read-only "Zero-Trust" switch ([Claudoo](https://cicdoo.com/claudoo)). If vitabot ships writes, users will expect these behaviours.

## Ten existing holes must close before a single write ships

A write feature inherits every weakness of the session that triggers it. The audit found the following problems in the current tree. Several of them would let a low-privilege or stolen session reach an admin action even if the write flow itself were perfect.

| # | Hole | Where | Why it blocks writes | Fix |
|---|---|---|---|---|
| 1 | `/users/import/confirm` and `/preview` have no role check. Confirm accepts roles `admin`/`editor`/`auditor` and sets the default password `Welcom123!` | `main.py:2536-2660`, `2614-2618` | Any member can mint vitabot admins, and those admins could then reach the action endpoints | Add `require_admin_or_company_admin` with company scoping. Restrict roles to the auth model's set. Generate random passwords plus a reset link |
| 2 | FAQ CRUD, `/media/link`, Excel row edits, FAQ-category admin routes and `/odoo/suggested-questions` have no role check | `main.py:2786-2840`, `2576-2585`, `1536-1624`, `3069-3100`; `routers/faq_categories.py:26-95` | Shows that role enforcement is per-handler and easy to forget, so a new `/odoo/actions/*` route is at risk of the same | Add `require_admin`. Add a test that lists every non-GET route and asserts a role dependency |
| 3 | Odoo SSO tokens default to **10 years** (`ODOO_SSO_TOKEN_EXPIRE_MINUTES = 10*365*24*60`) | `main.py:597` | A stolen token could approve writes for a decade unless `token_version` is bumped | Use short access tokens with refresh, plus step-up re-authentication (or the Odoo-side confirm below) for actions |
| 4 | `generate_odoo_token.py` mints HS256 admin JWTs valid for 365 days with hardcoded IDs. The `cpbot_vita_insights` widget sends such a static token from `ir.config_parameter` | `generate_odoo_token.py:1-13`; `cpbot_vita_insights/static/src/js/cpbot_chat_widget.js:50-66` | A shared, long-lived admin credential with no per-user identity | Retire it. Never enable write tools on that widget path |
| 5 | The legacy SSO path still accepts a single shared `X-Odoo-Sso-Secret`, matches by email only and returns the raw token in JSON | `main.py:816-899` | It bypasses the hardened per-client HMAC and the `odoo_identity` binding | Remove it once all clients run the hardened addon |
| 6 | `/odoo/ask` has no `@limiter.limit` and takes `history` from the request body | `main.py:3012-3051` | A caller can fabricate prior assistant turns, including fake "confirmations" | Rate-limit the route. Persist Ask Odoo conversations on the server. Never treat chat text as consent |
| 7 | `get_user_access_rights` uses an ilike match with limit 1 and returns all usernames on a miss. Any Vita Care member can query any user | `services/odoo_service.py:431-471` | Information disclosure, and wrong-person resolution | Resolve by exact id after disambiguation. Run lookups with the requester's visibility |
| 8 | Sync Anthropic, Gemini and XML-RPC calls run inside `async def` handlers on one uvicorn process | `main.py:1706, 1806, 1867, 3042`; `Dockerfile:22` | A slow Odoo write or confirm stalls every tenant's requests | Use `asyncio.to_thread` and multiple workers |
| 9 | CORS regex trusts any `*.onrender.com` origin with credentials | `main.py:130-148` | Widens the CSRF and token-theft surface for confirm endpoints | Pin exact origins |
| 10 | The SSO JWT lacks `company_id`, so an SSO user promoted to `company_admin` would get a 403 from `require_admin_or_company_admin` (an inference from the code; untested) | `main.py:786-796`; `core/auth.py:145-180` | Company-scoped approvers would not work | Add `company_id` (and `odoo_uid`) claims on the SSO path |

Three gaps outside this table also block a responsible launch. There is **no audit log of any admin action**: a grep for "audit" finds only the `auditor` role string. **Migrations are gitignored and missing from the repo**, so the RLS policies and schema cannot be reviewed (`.gitignore`; referenced in `core/auth.py:59-61`). And **there are no tests** for Odoo SSO verification, the Odoo agent or role enforcement, and no CI. Every one of these is a prerequisite, not a nice-to-have, for a feature that changes who can see a branch's data.

## Odoo enforces "who may edit users"; vitabot must add "only branches you hold"

In Odoo, a user's access to a company or branch is two fields on `res.users`. **`company_ids`** is a many2many of allowed companies. **`company_id`** is the required default company, and it must be one of them. An `@api.constrains` check raises "Company … is not in the allowed companies for user …" when the default falls outside the allowed set ([res_users.py 16.0 L544](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L544), [18.0 L589](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L589)). "Allow X on branch Y" therefore means linking Y into `company_ids` with command `(4, Y)`. "Disallow" means `(3, Y)`, which fails if Y is X's default company unless the same write moves `company_id` elsewhere.

Writing `company_ids` also silently links or unlinks `base.group_multi_company` depending on whether the user ends up with more than one company ([res_users.py 16.0 L1703-1724](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L1703)). The preview should say so, because a "pure branch change" does modify groups.

Odoo's ACLs settle the first half of the user's question. Write access on `res.users` belongs to `base.group_erp_manager` ("Access Rights"), which `base.group_system` ("Settings") implies. Ordinary internal users get read-only rows ([ir.model.access.csv 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/ir.model.access.csv); [base_groups.xml 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/base_groups.xml#L10)). A user editing their own record may touch only `SELF_WRITEABLE_FIELDS`, and `company_ids` is not among them ([res_users.py 18.0 L356](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L356)).

The second half, "only for branches I manage", **does not exist in Odoo**. The `res_company_rule_erp_manager` record rule gives Access Rights managers the domain `[(1,'=',1)]`, so they can see every company. Group rules are OR-ed, and many2many link commands do not check access on the target company ([base_security.xml 16.0 L146-173](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/security/base_security.xml#L146); [Odoo 18 docs: Security](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)). An Access Rights user can grant any branch to anyone. The source research also found nothing that stops them from adding `base.group_system` to someone, themselves included. That last point was not exhaustively verified, but it is reason enough never to expose generic `res.users` writes or group changes to the bot.

Asking Odoo whether an action is allowed works, but only from the right seat. In 16/17, `check_access_rights(op, raise_exception=False)` and `check_access_rule(op)` are public and callable over RPC. 18 replaces them with `check_access`/`has_access` and deprecates the old names. 19 makes `check_access` private ([models.py 16.0 L3522-3570](https://github.com/odoo/odoo/blob/16.0/odoo/models.py#L3522); [models.py 18.0 L4442-4540](https://github.com/odoo/odoo/blob/18.0/odoo/models.py#L4442)). In 16/17, `has_group` lets any authenticated caller check any user's groups ([res_users.py 16.0 L1055-1062](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L1055)).

The catch is that **these checks return "allowed" when evaluated under `sudo()`**, because `env.su` short-circuits them ([models.py 18.0 L4442-4464](https://github.com/odoo/odoo/blob/18.0/odoo/models.py#L4442)). They are just as meaningless under an admin service account. The check has to run as the requester's uid. That points directly at code running inside the addon under `request.env.user`, or under an env built for the requester with `su=False`.

### What carries over to Odoo 15, and what to verify

The research read Odoo 16–19 source, not 15. The table below separates what is safe to assume from what the team should confirm against the Odoo 15 branch before writing code.

| Topic | Evidence (16–19) | Odoo 15 expectation | Confidence |
|---|---|---|---|
| Multi-company via `res.users.company_ids` / `company_id`, the "default must be allowed" constraint, and auto `group_multi_company` | Identical in 16–19 (cited above) | Same model; the codebase already reads Odoo 15 `groups_id` (`services/odoo_service.py:435`) | High, but verify the constraint method name |
| `base.group_erp_manager` ACL on `res.users`; erp_manager sees all companies | 16–19 CSV and rules | Same group XML IDs are long-standing | High, verify the record rule |
| `check_access_rights` / `check_access_rule` public over RPC | 16/17 | Present | High |
| `has_group` on another user, unrestricted | 16/17 | Likely the same | Verify |
| Branches (`root_id`, delegated fields, fixed hierarchy, "Branches" tab) | Introduced in **17** ([res_company.py 17.0](https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/res_company.py#L34)) | **Absent.** A "branch" on 15 is just another `res.company`, possibly with a plain `parent_id` | High that the feature is absent |
| `auth='bearer'` routes, JSON-2 API, scoped API keys | 18+ / 19 ([Odoo 19 JSON-2](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)) | **Unavailable.** Use `auth='user'` or a signed `auth='public'` route plus XML-RPC | High |
| No chatter tracking on `res.users` | 17, 19 `mail` source | Likely the same, so explicit logging is needed | Verify |

Upgrading later carries a hard deadline. XML-RPC and JSON-RPC are scheduled for removal in **Odoo 22 (fall 2028) and Odoo Online 21.1 (winter 2027)** ([Odoo 19 JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)). Putting the write logic in an addon controller rather than in `execute_kw` calls protects the feature from that migration. It also keeps "check then write" inside one transaction, which JSON-2 cannot do across calls.

**"Branch" must be disambiguated first.** The Ask Odoo prompt already describes the warehouses tool as "warehouses/branches" (`services/odoo_agent.py:316-321`). In standard Odoo, per-user branch access is the company switch described above. Warehouse-level restrictions per user are not a base `res.users` field. If Vita Care's users mean warehouses, the permission lives in whatever custom record rule or module restricts warehouses, and that has to be identified before any tool is designed. This is an inference that needs confirming against the actual instances. Ask the product owner which one users mean. Then have the bot echo the resolved record type ("company Riyadh Branch" vs "warehouse RYD-WH") in every preview.

## The model proposes, vitabot records, Odoo executes as the requester

Every serious vendor converges on the same split. SAP binds a delegated agent to "a subset of what that user holds" ([SAP Joule Compliance Brief](https://www.sap.com/sweden/documents/2026/06/526001c1-567f-0010-bca6-c68f7e60039b.html)) and checks permissions at its gateway and again in the target application ([SAP Architecture Center](https://architecture.learning.sap.com/docs/ref-arch/RA0029/8)). ServiceNow limits an agent to the intersection of the user's roles and an approved list ([ServiceNow role masking](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/enable-ai-experiences/acls-and-rolemasking.html)). Salesforce re-checks the user's permissions when they confirm ([Agentforce Coworker](https://developer.salesforce.com/docs/data/agentforce-coworker/guide/agentforce-coworker-allow-coworker-update-records.html)). OWASP asks for execution "in the user's context" with "complete mediation" in downstream systems, "not by trusting the LLM's judgment" ([OWASP LLM06](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)).

For vitabot, the effective permission becomes **the requester's Odoo rights ∩ vitabot's allow-list of action types ∩ the tenant's enabled features.**

### Components and where they plug in

| Component | Plug point | Responsibility |
|---|---|---|
| Requester identity | `/odoo/ask` (`main.py:3022-3041`) | Select `odoo_identity` and parse the uid. Pass `requester_odoo_uid` into `odoo_agent_ask`. Never accept it from the body or the LLM |
| Read tools | `TOOLS` / `_TOOL_FUNCTIONS` (`services/odoo_agent.py:159-416`) | `find_users(query)` and `find_branches(query)` return candidate lists with id, name, login and current companies. `explain_user_access(user_id)` covers groups, allowed companies, default company, and whether *the requester* may change them. When there are multiple matches, the backend returns a structured "choose one" card instead of letting the model guess |
| Propose tool | Same registry, captured like `present_chart` (`services/odoo_agent.py:543-551`) | `propose_branch_access_change(target_user_id: int, company_id: int, action: grant/revoke)`. Accept only IDs that earlier lookups in this conversation returned. Create a pending row and return a preview. **No `execute_*` tool is ever declared to the model** |
| Pending-action table | New migration, committed this time | `odoo_pending_actions`: id, tenant_id, requester_user_id, requester_odoo_uid, client_key, operation (IDs only), before_state, after_state, risk_level, status, expires_at (about 5 min), decided_at, executed_at, result, error |
| Confirm/cancel | New `POST /odoo/actions/{id}/confirm` and `/cancel` with `require_*`, rate limits and CSRF | Re-check ownership, expiry, status and `before_state` (optimistic concurrency). Use the id as the idempotency key. Typed "yes" in chat never counts |
| Odoo action endpoint | New controller in `cpbot_vita_bot_link` next to `/vita_bot/sso` | Run under the requester's Odoo identity. Apply the custom branch policy. Write only `company_ids`/`company_id`. Support dry-run. Log in Odoo |
| Audit | New append-only `odoo_action_audit` plus `log_ai_prediction` label | Who, what, before/after, model, tool JSON, decision and reason, Odoo response, IP. Surface it in tenant analytics |
| UI card | Shared confirm dialog (`frontend/src/app/shared/confirm-dialog/`) in superadmin `odoo-chat` or a re-enabled `vita-insights` | "Grant Ahmed Al-Harbi (ahmed.h@…) access to company Riyadh Branch. Now: Jeddah, HQ → After: Jeddah, HQ, Riyadh." Confirm and Cancel buttons. Undo for N minutes through the same checks |

### Confirm inside Odoo, not inside vitabot

The addon can learn who the requester is in two ways, and the choice decides how much vitabot's own token hygiene matters.

**Option A (recommended for permission changes) has the user confirm on an Odoo-hosted page.** The chat card links to something like `{odoo}/vita_bot/action/confirm?proposal=…&sig=…`. The route is declared `auth='user'`, exactly like the existing `/vita_bot/sso` (`cpbot_vita_bot_link/controllers/sso.py:219-236`), so the request runs with the rights of the logged-in user ([http.py 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/http.py#L707)). The addon then:

1. verifies vitabot's HMAC over the proposal (proposal id, target, company, operation, requester uid, expiry), reusing the per-client secret already shared for SSO (`services/odoo_service.py:571-585`);
2. checks that `request.env.user.id` equals the proposal's requester;
3. recomputes the preview from live data;
4. executes on a CSRF-protected POST;
5. calls vitabot back with a signed result.

The signature proves vitabot issued the exact parameters. The Odoo session proves a human with those rights is present. So **a stolen 10-year vitabot token, a fabricated chat history or a hijacked model cannot complete a write.**

**Option B is a server-to-server signed call.** The addon builds an env for the requester with `su=False` and executes. The user stays in the chat, but the addon has to trust vitabot's assertion of who the requester is. A compromised backend could then act as any Access Rights user. Option B is acceptable only after holes 3–6 are closed and confirmation requires a fresh step-up. It suits lower-risk writes later.

Both options keep the service account read-only. Odoo itself recommends dedicated bot users "with minimal permissions" for integrations ([Odoo 19 JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)).

The addon policy is short but non-negotiable. The requester must hold `base.group_erp_manager`. The target branch must be in the requester's own `company_ids`. The target must be an internal user (`share=False`) who shares a company with the requester. Self-targeted changes are refused. A revoke that would leave the user with no company is refused, and a revoke of the default company moves `company_id` in the same write. The sketch below adapts the Odoo 16–18 pattern from the research to plain tuple commands, which work on 15. It is unverified on 15.

```python
@http.route('/vita_bot/action/branch_access', type='json', auth='user', methods=['POST'])
def branch_access(self, proposal, sig, dry_run=True):
    _verify_vitabot_hmac(proposal, sig)                 # same per-client secret as SSO; check expiry
    env, actor = request.env, request.env.user          # requester, NOT sudo
    if actor.id != int(proposal['requester_odoo_uid']):
        raise AccessError("This proposal belongs to another user.")
    if not actor.has_group('base.group_erp_manager'):
        raise AccessError("You need the Access Rights role to change user companies.")
    target = env['res.users'].browse(int(proposal['target_user_id'])).exists()
    company = env['res.company'].browse(int(proposal['company_id'])).exists()
    if not target or not company or target.share or target == actor:
        raise ValidationError("Invalid target.")
    if company not in actor.company_ids:                # the policy Odoo lacks
        raise AccessError("You can only manage branches you have access to.")
    vals = {'company_ids': [(4, company.id)]} if proposal['action'] == 'grant' else {'company_ids': [(3, company.id)]}
    if proposal['action'] == 'revoke' and company == target.company_id:
        remaining = target.company_ids - company
        if not remaining:
            raise ValidationError("Cannot remove the user's only company.")
        vals['company_id'] = remaining[0].id
    if dry_run:
        return {'before': target.company_ids.mapped('name'), 'vals': vals}
    target.write(vals)                                  # ACLs, rules, constraints enforced as actor
    target.partner_id.message_post(body=f"Allowed companies changed by {actor.name} via Vita Bot ({proposal['id']})")
    return {'after': target.company_ids.mapped('name')}
```

Two design choices keep prompt injection from mattering. First, **give the write-capable agent a separate "permissions admin" mode** that does not ingest free text. Today `odoo_agent_ask` injects KB excerpts and a sales summary into the system prompt (`services/odoo_agent.py:451-474`). Meta's "Rule of Two" says a session should not combine untrusted input, sensitive data and state changes without human supervision ([Meta AI](https://ai.meta.com/blog/practical-ai-agent-security/)), so the permissions mode should see only structured fields such as names, logins and company names. Second, rewrite the system prompt at `services/odoo_agent.py:90-99` so it explains the proposal flow honestly instead of forbidding all talk of change. The prompt is only guidance: "a system prompt is a soft instruction, and so is an injection" ([MindStudio](https://www.mindstudio.ai/blog/lethal-trifecta-prompt-injection)). The real guarantees are the missing `execute_*` tool, the ID allow-list, the confirmation the model cannot forge, and Odoo's checks.

Odoo does not track `res.users` changes in chatter by default. The `mail` module only inherits `res.users` without `mail.thread` ([mail/models/res_users.py 19.0](https://github.com/odoo/odoo/blob/19.0/addons/mail/models/res_users.py#L20)). That makes the explicit `message_post` on the partner, together with vitabot's own append-only audit, the only record of who changed access.

## Five phases put security first and writes last

| Phase | Scope | Exit criterion |
|---|---|---|
| **0. Harden** | Close holes 1–10. Commit migrations. Add CI with pytest, plus a route-role test and Odoo SSO signature tests. Add an `admin_audit` table for user CRUD, role changes, deletes and SSO provisioning | No mutating route lacks a role dependency. SSO tokens are short-lived. The legacy SSO path and the 365-day token are gone |
| **1. Explain access (read-only)** | Add `find_users`, `find_branches` and `explain_user_access`, plus a `can_i(action, target)` that runs the addon policy in dry-run. Lookups run as the requester (an `auth='user'` read endpoint in the addon) so visibility matches Odoo. Persist Ask Odoo conversations on the server | "Can I give Ahmed Riyadh?" returns the same verdict the write path would. No usernames leak on a miss |
| **2. Propose only** | `propose_branch_access_change` creates pending rows and preview cards with no execute button ("an Access Rights admin would do this"). A per-tenant `odoo_actions_enabled` flag replaces hardcoded tenant gating (`core/auth.py:185-228`) | Product owner confirms which "branch" users mean. Previews match Odoo state |
| **3. Confirmed single-branch writes** | Option A confirm page in `cpbot_vita_bot_link`, plus idempotency, undo, rate limits (for example N changes per requester per hour) and alerts on bulk, self-targeted or repeatedly denied attempts | Tests cover denial, a cross-company target, expired or replayed proposals and a fabricated `action_id`, following `tests/test_widget_sso.py` style |
| **4. Two-person rule** | Any group change (especially `base.group_system`), bulk changes, and changes affecting approvers require a second, different approver. The support-ticket model (`routers/support_tickets.py`) is a ready approval-queue pattern, and `get_area_admins` can route requests | Second-approver flow audited end to end |

Write actions are one feature among several, and the audit points to cheaper wins that make vitabot more credible as a whole. **Streaming answers and non-blocking calls** come first, because one slow LLM or Odoo call currently freezes the single worker. **Citations** come next: `/ask` already returns `sources` (`main.py:1882`), but no template renders them. The thumbs-down reason box is equally cheap, since the API accepts `feedback` while the UI always sends `null` (`chat-page.ts:545`). **Token and cost columns** on `ai_predictions_log` (`services/ai_monitoring.py:11-30`) would allow per-tenant cost dashboards and caps, which third-party Odoo AI apps already sell ([apps.odoo.com "chatgpt"](https://apps.odoo.com/apps/modules/browse?search=chatgpt&order=Downloads)). The digest is computed but not delivered, so **email delivery** is mostly plumbing (`routers/tenant_analytics.py:204-229`). On RAG quality, heading-aware chunking and a reranker would replace fixed 800-character chunks (`services/chunking.py`). A "weak answer → new FAQ" one-click workflow would turn the existing no-info detection into a curation loop. Performance needs attention too: `get_sales_summary` pulls every `sale.order` on each Ask Odoo question (`services/odoo_service.py:82-86`), so it needs caching or aggregation.

Positioning favours these investments. Odoo's native AI is Enterprise-only and runs on IAP credits at €1 each, and installing it on the Standard plan forces an upsell to Custom ([Odoo 20 docs: AI](https://www.odoo.com/documentation/20.0/applications/productivity/ai.html); [iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)). Native chats are kept for only 30 days ([Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)). Vitabot's openings are an Odoo 15 and Community-era base, flat pricing, long-term analytics with audit history, and Arabic quality.

Arabic quality is measurable. The Ask Odoo fallback strings are hardcoded in Levantine Arabic only (`services/odoo_agent.py:535, 573`). Vendors serving the region flag Arabic–English code-switching and Gulf dialect as requirements ([Logiolegion](https://logiolegion.com/blogs/ai-chatbot-development-saudi-arabia-whatsapp-arabic-nlp-pdpl-2026); [LetsBot](https://letsbot.net/en/blogs/whatsapp-bot-arabic-dialects-guide-2026.html)). Odoo's native agent framework has no WhatsApp bridge ([suite_whatsapp_ai](https://apps.odoo.com/apps/modules/19.0/suite_whatsapp_ai)), which makes a WhatsApp channel with ticket handoff a credible later bet. The demand evidence for it is mostly vendor-sourced, and it should never carry write actions, because a phone number is weaker identity than an Odoo session.

## Conclusion

The question "can the bot check that the requester is allowed to do this write?" turns out to be mostly the wrong framing. Vitabot should not be the one deciding. Once the write runs inside Odoo under the requester's own session, Odoo's ACLs already answer "may this person edit users?". Vitabot's job shrinks to three things Odoo cannot do: bind the request to a real person rather than an email in a prompt, enforce the single missing policy ("only branches you hold"), and make sure a human, not the model, presses the button.

That shift also moves the risk. The largest danger in shipping writes is not the LLM but vitabot's existing authorization: unguarded admin-creating endpoints, decade-long tokens and trusted client history. Confirming on an Odoo-hosted page is valuable because it makes those weaknesses irrelevant to permission changes while they are being fixed. The same identity and policy plumbing also fixes today's read-only feature, which currently lets any member look up anyone's access as the service account. The work is therefore worth doing even if writes never ship.
