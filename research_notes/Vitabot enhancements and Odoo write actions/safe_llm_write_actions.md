# Safe LLM Write Actions in an ERP (FastAPI + Gemini + Odoo)

Research date: 2026-11-10. Scope: architecture and security for letting a chatbot make changes in Odoo for a user (example: "allow user Ahmed on the Riyadh branch") only when the requesting user is authorized. Each claim has a source. Source dates are given where known.

---

## 1. Authorization patterns: enforce outside the LLM, act as the user, least privilege, confused deputy

### Takeaway
The model should only *propose* an action. A deterministic backend, and ideally Odoo's own ACLs and record rules, decides whether the action is allowed. Run it under the requesting user's identity, or a delegated subset of it, not a privileged service account. OWASP and all four enterprise vendors reviewed (Microsoft, Salesforce, SAP, ServiceNow) follow this approach.

### Cited Findings
- OWASP LLM06:2025 names three root causes of Excessive Agency: "excessive functionality; excessive permissions; excessive autonomy." It lists "a shared high-privilege account used instead of each user's own identity" as an example of excessive permissions. — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- OWASP LLM06 mitigations include:
  - "Execute extensions in the user's context", with per-user authentication and the smallest necessary scope.
  - "Enforce complete mediation", meaning every request is checked against security policy in downstream systems, "not by trusting the LLM's judgment".
  - "Minimize extension permissions" through the identity's actual privileges.
  — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- OWASP also says authorization should be implemented in downstream systems rather than relying on an LLM to decide whether an action is allowed. — [OWASP LLM06 (owasp.org mirror)](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM06_ExcessiveAgency.html)
- In the OWASP Agentic taxonomy, T3 "Privilege Compromise" maps to ASI03 "Identity and Privilege Abuse". One commentary calls it "the agentic evolution of Excessive Agency (LLM06:2025)". The source is secondary. — [NHI Mgmt Group guide](https://nhimg.org/complete-guide-to-the-2026-owasp-top-10-risks-for-agentic-applications); [Galileo on ASI02](https://galileo.ai/blog/owasp-agentic-ai-asi02-tool-misuse)
- **SAP Joule:** where an agent acts for a human user, "its permissions are bound to a subset of what that user holds. The agent cannot exceed the delegating user's authorization scope." — [SAP Joule Agents Compliance Brief (June 2026)](https://www.sap.com/sweden/documents/2026/06/526001c1-567f-0010-bca6-c68f7e60039b.html)
  - SAP's architecture FAQ says that for agents acting for a user, "the user context and applicable authorizations are propagated and enforced". — [SAP Architecture FAQ](https://architecture.learning.sap.com/docs/ai-native-north-star-architecture/frequently-asked-questions)
  - The SAP Agent Gateway checks user and tool permissions before the target application applies its own role-based authorization. That is two layers. — [SAP Architecture Center ref-arch](https://architecture.learning.sap.com/docs/ref-arch/RA0029/8)
- **ServiceNow:** the agent's roles are limited to the intersection of the invoking user's roles and an approved list ("role masking"). Each agent and agentic workflow needs its own ACL, and a user who fails the ACL cannot reach the agent at all. — [ServiceNow: ACLs, role masking, and user identities in AI Agent Studio (Zurich)](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/enable-ai-experiences/acls-and-rolemasking.html); [ServiceNow: Implement access control in Now Assist AI agents](https://www.servicenow.com/docs/r/intelligent-experiences/enable-ai-experiences/aia-security-implementation.html)
- **Salesforce:**
  - Agentforce Coworker creates and modifies records with the current user's permissions. Those permissions are checked when the user confirms. If they are insufficient, the create or update fails. — [Salesforce Developers: Agentforce Coworker create/update records](https://developer.salesforce.com/docs/data/agentforce-coworker/guide/agentforce-coworker-allow-coworker-update-records.html)
  - Autonomous/service agents instead run as a dedicated "agent user" and can see whatever that user can see. — [SalesforceBen: Agentforce permissions explained](https://www.salesforceben.com/agentforce-permissions-explained-agent-users-access-and-security/)
- **Microsoft:** Copilot for Service "uses your organization's existing access controls and user permissions from the CRM system". — [Microsoft Learn: Copilot for Service roles and privileges](https://learn.microsoft.com/en-us/microsoft-copilot-service/roles-and-privileges)
  - For the Sales agent, changes to CRM permissions can take up to 15 minutes to take effect. — [Microsoft Learn: Sales Copilot privileges](https://learn.microsoft.com/en-us/microsoft-sales-copilot/privileges)
- **MCP spec on confused deputy:**
  - The MCP authorization spec forbids token passthrough: "The MCP server MUST NOT pass through the token it received from the MCP client."
  - Servers "MUST only accept tokens specifically intended for themselves".
  - It warns that a server forwarding tokens downstream can cause the "confused deputy" problem.
  — [MCP Authorization spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- OAuth 2.0 Token Exchange (RFC 8693) is the standard way to swap a user's token for a downstream token, covering delegation and impersonation. This is the formal "on-behalf-of" pattern. — [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693)
- Odoo enforces access rights (model-level ACLs, `ir.model.access`) and record rules (`ir.rule`) per user for ORM operations done as that user. — [Odoo 18 developer docs: Security in Odoo](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)

### Inferences
- **For Vitabot (FastAPI + Odoo):** the safest pattern is two independent checks.
  - (a) A FastAPI policy layer checks that the *requesting* Odoo user may manage the target user and branch, for example has `base.group_erp_manager` or a custom "branch admin" group scoped to that branch.
  - (b) The actual write goes to Odoo *as the requesting user*, using their session or API key from the existing SSO link (`cpbot_vita_bot_link/controllers/sso.py`), so Odoo ACLs and record rules apply again.
  - If a service account must be used, the backend has to repeat Odoo's checks itself. It can use `has_group` / `check_access_rights` on the requester via an Odoo server-side method that takes the requester's uid, and must never trust the LLM.
- **Confused deputy for Vitabot:** the bot's service account holds admin rights, and the LLM decides who "the user" is. Any user who can talk to the bot, or any text the bot reads, could then trigger admin actions. The requester's identity must come from the authenticated session (JWT/SSO), never from the conversation or tool arguments.
- In Odoo, a "branch" is usually a `res.company` (multi-company / branches in Odoo 17+). "Allow Ahmed on Riyadh" then means adding the company to `res.users.company_ids`, a sensitive security field. Treat it as a high-risk write.

### Gaps
- I did not fetch Microsoft's official Entra on-behalf-of flow docs, or Odoo's OAuth / API-key scoping docs for Odoo 18/19. Check whether Odoo API keys can be scoped. The ivnvxd README mentions an `rpc` scope on Odoo 20 (see section 6).
- I found no official Microsoft document that says Dynamics 365 Copilot write actions are re-authorized per security role at confirmation time.

---

## 2. Function/tool calling design: narrow typed tools, validation, entity resolution, Gemini specifics

### Takeaway
Expose a small set of narrow, strongly typed tools. Examples: `set_user_branch_access(target_user_id, company_id, allowed: bool)` and `explain_user_access(user_id)`, rather than a generic `execute_kw(model, method, args)`. Validate every argument on the server, and resolve names to IDs in a separate read-only step that asks the user to pick when there is more than one match. With Gemini, limit which tools are callable per conversation stage, and let the application run each call, not the SDK.

### Cited Findings
- OWASP lists open-ended extensions ("generic shell or URL fetchers") as excessive functionality and recommends narrow, purpose-built tools. It also says to "minimize extension functionality" so each tool does only its job. Its example is a read-only document tool that also has delete/modify functions. — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- **Gemini function calling (current docs, 2026):**
  - Declarations have `name`, `description`, and `parameters` (`type`, `properties`, `required`).
  - Modes:
    - **auto** (default): the model decides.
    - **any**: "constrained to always predict a function call".
    - **none**: function calls are prohibited.
    - **validated**: "ensures function schema adherence".
  - Calls can be restricted to a subset of tools with `allowed_tools`.
  - "The model doesn't run functions itself": the application extracts the name and arguments, executes the call, and returns a `function_result`.
  - Gemini 3 models use thought signatures, which "the SDKs automatically handle".
  - Parallel and compositional (chained) calls are supported.
  — [Google AI Studio docs: Function calling](https://aistudio.google.com/docs/function-calling). Note: `ai.google.dev/gemini-api/docs/function-calling` now 301-redirects here. No last-updated date was visible.
- **Gemini best practices from the same page:**
  - "Be clear and specific" in descriptions.
  - "Use specific types (integer, string, enum)".
  - "Keep active set to 10-20 tools maximum".
  - "Validate function calls before executing".
  - "Implement robust error handling".
  - "Use appropriate authentication for external APIs".
  — [Google AI Studio docs: Function calling](https://aistudio.google.com/docs/function-calling)
- The `generateContent` / Vertex API uses `tool_config.function_calling_config` with `mode: ANY` and `allowed_function_names: [...]`. `allowed_function_names` can only be set when the mode is ANY, and the names must match a `FunctionDeclaration.name`. — [Gemini API function calling (ai.google.dev legacy URL)](https://ai.google.dev/docs/function_calling); [Google Cloud FunctionCallingConfig REST reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/Shared.Types/FunctionCallingConfig); [Function calling reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/function-calling)
  - **Conflict note:** the newer AI Studio page (Interactions-style API) uses lowercase modes under `tool_choice` with `allowed_tools`. The `generateContent` reference uses uppercase `ANY` with `allowed_function_names`. Check which API surface `services/llm.py` uses.
- The OWASP Agentic taxonomy (T2 / ASI02 "Tool Misuse") says agents can be manipulated into abusing tools they are *authorized* to use, causing harm "while staying within granted permissions". Narrow tools limit what a manipulated call can do. Source is secondary. — [Galileo: OWASP ASI02](https://galileo.ai/blog/owasp-agentic-ai-asi02-tool-misuse)

### Inferences
- **Recommended tool set for the branch-access use case:**
  1. `find_users(query: str) -> [{id, name, login, current_companies}]` (read-only)
  2. `find_branches(query: str) -> [{id, name}]` (read-only)
  3. `explain_user_access(user_id: int)` (read-only)
  4. `propose_branch_access_change(target_user_id: int, company_id: int, action: enum["grant","revoke"])`. This returns a *proposal*. It does **not** execute.

  Execution happens through a separate HTTP endpoint triggered by a UI button. That endpoint is not exposed to the model at all.
- **Do not let the model pass free-text names to write tools.** Require integer IDs that came from an earlier lookup in the same session. The server can track which IDs were returned to this user and reject IDs that weren't, which also blocks IDs smuggled in through injected text.
- **Disambiguation:** if `find_users("Ahmed")` returns more than one match, the backend, not the model, returns a structured "choose one" response. The UI shows it as selectable cards (name, login/email, department, current branches). The model should not guess.
- **Gemini configuration:**
  - Use `mode=AUTO` (or `VALIDATED`) with only read tools plus `propose_*` declared.
  - Never declare an `execute_*` tool to the model.
  - Turn off Python SDK automatic function calling for any tool with side effects, so FastAPI runs the call.
  - Always check that `function_call.name` is in a server-side allowlist, and validate `args` with Pydantic models before running anything.

### Gaps
- I could not read the part of the AI Studio page covering automatic function calling. Confirm in the `google-genai` SDK docs how to disable it (believed to be `automatic_function_calling={"disable": True}`). Not verified this session.
- I found no Gemini doc text that explicitly recommends getting user confirmation before consequential actions. The excerpt I read did not include one.

---

## 3. Human-in-the-loop: propose, preview, confirm, execute, result

### Takeaway
All four vendors reviewed, and OWASP, require explicit human confirmation for consequential writes. The best pattern runs in this order:
1. A server-side proposal object, with a dry-run diff.
2. A UI confirmation button bound to a single-use, expiring token tied to the user and the exact parameters.
3. Re-authorization when the button is clicked.
4. Idempotent execution.
5. A result message, plus an undo option where possible.

Two-person approval should cover the highest-risk changes, such as granting admin or security groups.

### Cited Findings
- OWASP LLM06: "Require user approval" for high-impact actions. Its example mitigation for an email agent is to require the user to manually approve every outgoing email. — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- **SAP:** the Joule design system says to "use a confirmation step for high-stakes or irreversible actions", and not when the action can easily be undone or needs no input. — [SAP Fiori design for iOS: Joule Confirmation Step (v26.4)](https://www.sap.com/design-system/fiori-design-ios/v26-4/joule/patterns/joule-confirmation)
  - An SAP warehouse agent guide describes a YES/NO confirmation. No operation runs without explicit user confirmation. — [SAP MAO Warehouse Agent Configuration Guide](https://api.sap.com/odata/1.0/catalog.svc/Files('MAO_Warehouse_Agent_Configuration_Guide')/$value)
  - A third-party SAP playbook says confirmation gates use "Joule confirmation cards, SAP Build Process Automation approval steps, or SAP Task Center tasks, all creating a traceable audit log". This source is secondary. — [SAP playbook (third-party)](https://sap-playbook.pages.dev/agentic-ai/)
- **ServiceNow:** tools in "supervised" mode need human review before significant changes run. In Flow Designer's "Use an AI agent" action, a Support User reviews and authorizes the agent's work, and the flow pauses until they respond. — [ServiceNow: Use an AI agent action (Zurich)](https://www.servicenow.com/docs/r/zurich/build-workflows/workflow-studio/use-an-ai-agent-action.html)
  - A third-party guide warns that supervised mode does not fix an overly broad audience or identity. — [macmyths guide](https://macmyths.com/how-to-set-up-and-govern-ai-agents-in-servicenow/)
- **Microsoft:** a Microsoft Q&A answer (community, not official docs) says declarative Copilot agents must get user confirmation before consequential actions. It adds that the confirmation cannot be turned off globally, though the text can be customized. — [Microsoft Q&A](https://learn.microsoft.com/en-my/answers/questions/5921449/copilot-declarative-agent-always-shows-confirmatio)
  - Copilot Studio has a per-tool "Ask the user before running this action" setting, per a third-party guide. — [FSI-AgentGov control 1.18](https://judeper.github.io/FSI-AgentGov/controls/pillar-1-security/1.18-application-level-authorization-and-role-based-access-control-rbac/)
- **Salesforce:** Agentforce Coworker checks permissions when the user *confirms* a create/update. — [Salesforce Developers](https://developer.salesforce.com/docs/data/agentforce-coworker/guide/agentforce-coworker-allow-coworker-update-records.html)
  - Salesforce ISV guidance says private actions that create, delete, or alter records should, at a minimum, require user verification and be given only to verified users. — [Salesforce: Secure Your Agentforce Custom Actions](https://developer.salesforce.com/docs/platform/isvforce/guide/secure-agentforce-actions.html)
- **Bypassing confirmation is a real attack outcome.** In a reported incident, a poisoned PR told an AI coding assistant to delete AWS resources. The flags `--trust-all-tools --no-interactive` had disabled all confirmation prompts. Source is secondary. — [NHI Mgmt Group guide](https://nhimg.org/complete-guide-to-the-2026-owasp-top-10-risks-for-agentic-applications)

### Inferences
These are my design recommendations. No single source spells out this exact flow.
- **Proposal record:** stored server-side in Postgres/Redis with these fields:
  - `proposal_id` (UUID)
  - `requester_uid` (from the session)
  - `tenant_id`
  - `tool`
  - `normalized_params` (IDs only)
  - `before_state` snapshot (current `company_ids` of the target user)
  - `after_state` diff
  - `risk_level`
  - `expires_at` (for example 5 minutes)
  - `status`
- **Preview:** the UI shows a card such as "Grant Ahmed Al-Harbi (ahmed.h@...) access to company 'Riyadh Branch'. Current: Jeddah, HQ. After: Jeddah, HQ, Riyadh." The card has Confirm and Cancel buttons.
- **Confirm button:**
  - It POSTs `/actions/{proposal_id}/confirm` with a CSRF-protected, single-use confirmation token (HMAC of `proposal_id` + `requester_uid` + params hash + expiry).
  - Typed "yes" in chat should **not** count. The model or injected content could produce it, and it cannot be bound to exact parameters.
- **When confirm is clicked:**
  - Check that the session user equals `requester_uid`.
  - Re-check authorization against live Odoo data, because permissions may have changed.
  - Check that `before_state` still matches (optimistic concurrency).
  - Execute with `proposal_id` as the idempotency key, so a double-click or retry cannot apply the change twice.
- **Undo:** store the inverse operation, for example a revoke of the company just granted, and offer an "Undo" button for N minutes. Undo goes through the same authorization check.
- **Two-person rule:** some changes need a second approver with the right role, who must be a different user. Examples: adding security groups such as `base.group_system` or Settings admin, changes to more than N users, or changes to the requester's own account.
- **Self-modification:** requests by a user to change their own permissions should be blocked outright, or always need a second approver.

### Gaps
- I found no vendor doc that specifies idempotency keys or expiring confirmation tokens for agent actions. These are standard API practices applied here by inference.

---

## 4. Security threats and mitigations (OWASP LLM Top 10 2025, OWASP Agentic, prompt injection)

### Takeaway
Prompt injection, both direct and indirect (through ERP record text, chatter, uploaded documents), is unsolved. Design so that a fully hijacked model still cannot do harm. The model's tools stay narrow and propose-only, authorization is deterministic and tied to the session identity, and every write needs a human confirmation that the model cannot forge. Meta's "Agents Rule of Two" is a useful design budget.

### Cited Findings
- OWASP LLM06 lists hallucination and prompt injection (direct, indirect, or via a compromised extension or peer agent) as triggers for Excessive Agency.
  - **Example attack:** a hidden instruction in an email makes an email-summarizing assistant search the inbox and forward sensitive data.
  - **Fixes it proposes:** read-only functions, a read-only OAuth scope, and manual approval of every send.
  - It also says logging, monitoring, and rate limiting "won't prevent Excessive Agency" but can limit the damage.
  — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- OWASP released the "Top 10 for Agentic Applications" on 2025-12-09. It builds on the Agentic AI Threats & Mitigations taxonomy (T2 Tool Misuse maps to ASI02, T3 Privilege Compromise to ASI03). — [OWASP GenAI announcement (2025-12-09)](https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/); [InfoQ coverage (2025-09)](https://www.infoq.com/news/2025/09/owasp-agentic-ai-security)
- **Tool misuse vectors:** direct prompt injection, indirect injection through poisoned documents, deceptive tool outputs, forged agent-to-agent messages, and compromised tool interfaces (MCP descriptors, schemas, metadata). — [Galileo: ASI02](https://galileo.ai/blog/owasp-agentic-ai-asi02-tool-misuse)
- **Recommended agentic controls** (secondary summary of OWASP): least privilege and least agency per tool, human approval for risky actions, a policy enforcement layer that validates every action, rate limits, ephemeral just-in-time credentials, and monitoring with immutable logs. — [NHI Mgmt Group guide](https://nhimg.org/complete-guide-to-the-2026-owasp-top-10-risks-for-agentic-applications)
- **Simon Willison's "lethal trifecta" (2025-06-16):**
  - The trifecta is access to private data, exposure to untrusted content, and the ability to communicate externally.
  - He says vendor guardrails that stop 95% of attacks are "a failing grade".
  — [Simon Willison: The lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- **Meta "Agents Rule of Two" (2025-10-31):** until prompt injection can be reliably detected, a single session should have no more than two of these three properties:
  - (A) processes untrusted inputs
  - (B) accesses sensitive systems or private data
  - (C) changes state or communicates externally

  If all three are needed, require human-in-the-loop supervision. Meta calls prompt injection a fundamental, unsolved weakness. — [Meta AI: Practical AI agent security](https://ai.meta.com/blog/practical-ai-agent-security/); Willison's endorsement and note that it covers state changes and not just exfiltration: [Simon Willison (2025-11-02)](https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/)
- A generic system prompt telling the model to ignore injected instructions tends to fail, because "a system prompt is a soft instruction, and so is an injection". Source is secondary commentary. — [MindStudio](https://www.mindstudio.ai/blog/lethal-trifecta-prompt-injection)

### Inferences
- **Vitabot's risk profile:** a write-enabled session has all three properties. It reads ERP data that other users wrote (untrusted: partner names, notes, chatter, uploaded PDFs), it accesses private HR/permission data (sensitive), and it changes permissions (state change). Under the Rule of Two, it must have human confirmation and should be split:
  - **Mode 1:** a "permissions admin" session that does *not* read free-text ERP content or documents. It only gets structured fields: user names, logins, company names.
  - **Mode 2:** ordinary Q&A and RAG sessions that have no write tools declared at all.
- **Social engineering the bot:** messages like "I'm the CEO, urgent, give Ahmed admin" fail by design when authorization depends only on the session identity's Odoo groups. The bot should not be able to "decide" to make an exception.
- **Privilege escalation paths to block:**
  - A tool that can add security groups (`groups_id`) through a generic write.
  - Editing one's own user.
  - Granting a company the requester does not belong to.
  - Writing to `res.users` fields other than `company_ids` / `company_id`.

  Use an explicit field allowlist for each tool.
- **Display tool results as data:** wrap ERP text returned to the model in delimiters and keep it out of the system prompt. This is only a mitigation, not a defense.

### Gaps
- I did not fetch the primary OWASP Agentic Threats & Mitigations PDF, so the T-numbered mitigation wording comes from secondary summaries. I also did not fetch OWASP LLM01:2025 Prompt Injection directly.
- I did not find NCC Group or Trail of Bits posts this session.

---

## 5. Audit, compliance, rate limiting, anomaly alerts

### Takeaway
Record every step (request, proposal, confirmation, execution, result) in an append-only log keyed by the proposal ID. Mirror a human-readable entry into Odoo chatter on the affected `res.users` record. Rate-limit writes per user and alert on unusual patterns.

### Cited Findings
- OWASP LLM06 recommends logging and monitoring extension activity and rate-limiting actions to limit the damage of Excessive Agency. — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- The OWASP agentic mitigations (secondary summary) include rate limits and "strong monitoring with immutable logs". — [NHI Mgmt Group guide](https://nhimg.org/complete-guide-to-the-2026-owasp-top-10-risks-for-agentic-applications)
- SAP confirmation gates (Joule confirmation cards, Build Process Automation, Task Center) are described as creating a traceable audit log. Third-party source. — [SAP playbook](https://sap-playbook.pages.dev/agentic-ai/)
- The ivnvxd Odoo MCP server includes a tool to post chatter messages, showing that the Odoo chatter (`mail.thread` `message_post`) is reachable over RPC. — [ivnvxd/mcp-server-odoo](https://github.com/ivnvxd/mcp-server-odoo)

### Inferences
- **Audit record fields:**
  - `ts`
  - `tenant_id`
  - `requester_uid` and `login`
  - client IP / session id
  - raw user utterance
  - model name and version
  - tool call JSON proposed by the model
  - normalized proposal
  - authorization decision and reason
  - confirmer uid (and second approver)
  - confirmation timestamp
  - execution payload
  - Odoo response / error
  - `before_state` and `after_state`
  - `proposal_id` (idempotency key)
- **Immutability:** use an append-only table with no UPDATE/DELETE grants, or hash-chain the rows, or ship them to external log storage.
- **Mirror into Odoo:** call `message_post` on the target `res.users` (or `res.partner`) record, for example "Branch Riyadh granted by Sara via Vitabot (proposal abc123)". Odoo admins then see it in their normal tooling.
- **Rate limits:** for example, at most N permission changes per requester per hour, and at most M per tenant per day. Alert on bulk changes, changes outside business hours, self-targeted attempts, repeated authorization denials (probing), and any attempt to grant admin groups.

### Gaps
- I found no source covering a specific compliance regime (for example Saudi PDPL or ISO 27001 controls) for AI agent audit trails. Not researched.

---

## 6. MCP as an option: Odoo MCP servers, MCP auth spec, adopt or integrate directly

### Takeaway
Several open-source Odoo MCP servers exist. The most mature one (ivnvxd, about 415 stars) has a companion Odoo module that enforces a per-model CRUD allowlist on top of Odoo ACLs. However, these servers expose *generic* CRUD tools, which is the excessive-functionality pattern OWASP warns against. For a single, controlled FastAPI + Gemini backend, direct integration with narrow custom tools is safer and simpler. MCP's main value is interoperability with outside clients such as Claude Desktop or IDEs. If MCP is used later, its OAuth 2.1 spec must be followed strictly.

### Cited Findings
- **ivnvxd/mcp-server-odoo:**
  - **Read tools:** search, get record, describe fields, list models, aggregate, attachments, user context.
  - **Write tools:** create/update (single and batch), delete, upload attachments, post chatter messages.
  - **Gated tool:** `call_model_method` is registered only when `ODOO_YOLO=true` and `ODOO_MCP_ENABLE_METHOD_CALLS=true`.
  - **Permissions:** in standard mode, a companion Odoo module enforces a per-model allowlist with read/write/create/delete permissions. Users must be in the "MCP User" group, and Odoo access rights and record rules still apply. YOLO mode bypasses MCP controls and is for development only.
  - **Safeguards:** batch writes capped at 100 and transactional, `ir.actions.*` / `ir.cron` blocked, credential-like fields withheld. Multi-company scoping "is context-level, not a security boundary."
  - **Transport:** stdio, or streamable-http with *no built-in client authentication*. A reverse proxy is needed for remote use.
  - **Other details:** auth by API key or username/password, with an `rpc` scope on Odoo 20. Supports Odoo 16+. MPL-2.0. About 415 stars and 191 forks. No releases listed.
  — [GitHub: ivnvxd/mcp-server-odoo](https://github.com/ivnvxd/mcp-server-odoo)
- Other Odoo MCP servers: deeprunnerai/odoo-mcp-server (read/write across Inventory, CRM, Sales, MRP, Purchase), keboola/odoo-mcp-server (Odoo 18, says it includes OAuth 2.1 authorization and Docker), heimerle/odoo-mcp-server (13 tools, npm), tuanle96/mcp-odoo (MIT), pandeussilvae/mcp-odoo-panda, sameeroz/odoo-mcp-server. Maintenance status was not checked. — [deeprunnerai](https://github.com/deeprunnerai/odoo-mcp-server); [keboola](https://github.com/keboola/odoo-mcp-server); [heimerle](https://github.com/heimerle/odoo-mcp-server); [sameeroz](https://github.com/sameeroz/odoo-mcp-server); [tuanle96 (ecosyste.ms)](https://awesome.ecosyste.ms/projects/github.com%2Ftuanle96%2Fmcp-odoo); [mcp-server-odoo on PyPI](https://pypi.org/project/mcp-server-odoo/)
- **MCP Authorization spec (2025-06-18):**
  - Authorization is OPTIONAL. HTTP transports SHOULD conform. STDIO SHOULD NOT and instead takes credentials from the environment.
  - Authorization servers MUST implement OAuth 2.1.
  - MCP servers MUST implement Protected Resource Metadata (RFC 9728).
  - Clients MUST use Resource Indicators (RFC 8707), MUST use PKCE, and MUST NOT put tokens in query strings.
  - Servers MUST validate audience and MUST NOT accept or pass through other tokens.
  - Authorization servers SHOULD issue short-lived tokens and MUST rotate refresh tokens for public clients.
  — [MCP Authorization spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- Gemini 3 / AI Studio supports Remote MCP servers as tools, with an `allowed_tools` parameter to "restrict which tools from the server the agent may call". — [Google AI Studio docs: Function calling](https://aistudio.google.com/docs/function-calling)
- Willison's canonical lethal-trifecta example is a GitHub MCP exploit. A single server read attacker-filed public issues, accessed private repos, and opened PRs that leaked private data. — [Simon Willison (2025-06-16)](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)

### Inferences
- **Recommendation: direct integration first.** Vitabot already has an Odoo module (`cpbot_vita_bot_link`) with SSO. Adding a narrow, server-side Odoo controller is the tightest design, for example `/vitabot/action/branch_access/preview` and `/vitabot/action/branch_access/apply`. Each runs `with_user(requester)` with its own checks and posts to chatter. It also keeps validation inside Odoo, where record rules live.
- **If MCP is adopted:**
  - Build a *custom* MCP server with only the narrow tools.
  - Run it behind OAuth 2.1 with audience-bound tokens issued per Odoo user.
  - Never enable YOLO or `call_model_method`.
  - Do not expose generic `create/update/delete` on `res.users`.
  - Note that ivnvxd's multi-company scoping is not a security boundary. That matters directly for a branch-access feature.

### Gaps
- The MCP spec has newer revisions after 2025-06-18 (reportedly 2025-11-25, with changes to client registration). I did not verify them this session. Check the latest `/specification/` page before implementing.
- I did not check the keboola server's OAuth implementation or the activity of the other repos.

---

## 7. "Can I do X?": read-only permission explanation as a first step

### Takeaway
Start with a read-only "explain access" capability. It answers questions like "what branches can Ahmed access?" or "can I grant branch access?" from Odoo's own data and permission checks. It gives the bot useful value with no write risk, and its pieces (identity, entity resolution, permission checks) are the same ones the write flow will need.

### Cited Findings
- OWASP's mitigation for the email-agent scenario is to "include only read functionality" and use a read-only OAuth scope when writes aren't needed. — [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- SAP's guidance is to skip confirmation for steps that need no input or are easily undone, and to reserve it for high-stakes actions. Read-only answers need no gate. — [SAP Joule Confirmation Step](https://www.sap.com/design-system/fiori-design-ios/v26-4/joule/patterns/joule-confirmation)
- Under Meta's Rule of Two, a session without state-changing ability (property C) can safely handle untrusted input plus sensitive data, within limits. — [Meta AI blog](https://ai.meta.com/blog/practical-ai-agent-security/)
- Odoo's ACLs and record rules, and the group membership model, provide the data that defines a user's rights. — [Odoo 18: Security in Odoo](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)

### Inferences
- `explain_user_access(user_id)` returns the user's groups (`groups_id` names), allowed companies (`company_ids`), default company, and whether the *requester* may change them.
- `can_i(action, target)` runs the exact authorization function the write path will use, in dry-run mode. This means read and write share one policy engine and cannot drift apart.
- Even read-only answers must respect visibility. Requesters should only see users and companies their own Odoo rights allow. That means reading as the requester, not as admin.
- **Phased rollout:**
  1. Read-only explanations.
  2. Propose-only, showing "here's what an admin would do" with no execute button.
  3. Confirmed writes for low-risk changes.
  4. Two-person approval for high-risk changes.

### Gaps
- I found no vendor documentation for an "explain my permissions" agent feature. The recommendation is my inference.

---

## 8. Real-world vendor examples (Microsoft, Salesforce, SAP, ServiceNow)

### Takeaway
All four vendors (a) bind agent actions to the invoking user's permissions, or to a restricted subset or intersection of them, when acting for a user, and (b) offer or require confirmation or approval before consequential writes. Autonomous agents with no user present run under a dedicated agent identity with its own least-privilege roles.

### Cited Findings
- **Microsoft:**
  - Copilot for Service uses existing CRM access controls and user permissions. — [Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-copilot-service/roles-and-privileges)
  - Sales agent permission changes can take up to 15 minutes to apply. — [Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-sales-copilot/privileges)
  - Dynamics 365 F&O agents are deployed as managed solutions with an agent user that is assigned Dataverse security roles. — [Dynamics 365 agent deployment (mirror of Microsoft Learn)](https://dotnet.territoriali.olinfo.it/sv-se/dynamics365/fin-ops-core/dev-itpro/copilot/agent-deployment)
  - Declarative agents require confirmation for consequential actions. Community answer. — [Microsoft Q&A](https://learn.microsoft.com/en-my/answers/questions/5921449/copilot-declarative-agent-always-shows-confirmatio)
  - Microsoft Security blog on authorization and identity governance inside AI agents. — [Microsoft Tech Community](https://techcommunity.microsoft.com/blog/microsoft-security-blog/authorization-and-identity-governance-inside-ai-agents/4496977). Not fetched.
- **Salesforce:**
  - Agentforce Coworker uses the current user's permissions, checked when they confirm. — [Salesforce Developers](https://developer.salesforce.com/docs/data/agentforce-coworker/guide/agentforce-coworker-allow-coworker-update-records.html)
  - Service agents run as a dedicated agent user. — [SalesforceBen](https://www.salesforceben.com/agentforce-permissions-explained-agent-users-access-and-security/)
  - Private actions need user verification. — [Salesforce ISV guide](https://developer.salesforce.com/docs/platform/isvforce/guide/secure-agentforce-actions.html)
- **SAP:**
  - Joule agents are bound to a subset of the delegating user's authorizations. — [SAP Compliance Brief (2026-06)](https://www.sap.com/sweden/documents/2026/06/526001c1-567f-0010-bca6-c68f7e60039b.html)
  - The Agent Gateway checks permissions, then the target application checks again. — [SAP Architecture Center](https://architecture.learning.sap.com/docs/ref-arch/RA0029/8)
  - Confirmation step design pattern. — [SAP Fiori Joule](https://www.sap.com/design-system/fiori-design-ios/v26-4/joule/patterns/joule-confirmation)
- **ServiceNow:** role masking (intersection of the user's roles and an approved list), a per-agent ACL, supervised mode for tools, and a Support User approval that pauses the flow. — [ServiceNow ACLs & role masking](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/enable-ai-experiences/acls-and-rolemasking.html); [ServiceNow Use an AI agent action](https://www.servicenow.com/docs/r/zurich/build-workflows/workflow-studio/use-an-ai-agent-action.html)

### Inferences
- **ServiceNow's role-masking intersection** is a good model for Vitabot. The effective permission is the requester's Odoo rights ∩ the bot's allowlist of action types ∩ the per-tenant enabled features.
- **SAP's double check** (gateway, then application) maps to a FastAPI policy check followed by Odoo's ACLs and record rules when the call runs as the user.

### Gaps
- I found no Odoo vendor (Odoo S.A.) documentation on AI agent write actions in Odoo 18/19 AI features. Not researched this session.
- Some vendor findings come from community answers or third-party mirrors, as noted. Check them against current official documentation before quoting them externally.
