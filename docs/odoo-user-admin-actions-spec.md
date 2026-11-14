# Vita Bot: User Administration Actions in Odoo (Spec for the Odoo Team)

**Status:** Draft for review
**Odoo version:** 15 (client servers run Python 3.9, so no 3.10+ syntax)
**Addon:** extend the existing `cpbot_vita_bot_link` module (new version `15.0.1.1.0`)

---

## 1. Goal

Let a Pharmacy Manager do routine user administration by chatting with Vita Bot instead of clicking through Odoo screens:

1. **Ask about permissions.** Examples: "What can Mohamed Elsayed do?", "Who can edit prices at Wadi Jaleel 3?"
2. **Change permissions.** Add or remove a specific set of access rights, and change which branches and POS a user is allowed to use.
3. **Deactivate (and reactivate) users.**

The two scenarios in [section 8](#8-scenarios) are the acceptance tests.

## 2. The core rule: the bot can only do what the manager can already do

Every write runs **as the manager's own Odoo user**, with Odoo's normal access rights and record rules. Vita Bot adds **no extra power**: if Ahmed Fadl cannot make a change by hand in the Odoo UI, he cannot make it through Vita Bot either.

On top of that, the bot is **narrower** than the UI. It can only:

- run a short fixed list of actions;
- touch a set of permission groups that the client's admin explicitly allows;
- change normal staff users, never admins or the manager themselves.

### Risk-reduction principles (please keep all of them)

| # | Principle | Why |
|---|---|---|
| R1 | **No `sudo()` anywhere** in the new code, including lookups, logging and secret reading. | Every Odoo security check stays in force. See §5.3 for how each place avoids it. |
| R2 | **A fixed list of actions.** Never accept a model or method name from the request. | Even a stolen secret can't run arbitrary methods. |
| R3 | **Group allowlist.** The bot may add or remove only groups listed in Settings. | A bug or a misread prompt can't grant "Settings / Administrator". |
| R4 | **Preview, then confirm.** Every write is first called with `dry_run: true`. Odoo returns exactly what would change. The real write happens only after the manager clicks Confirm in Vita Bot. | The AI never changes data by itself, and a person sees the exact change first. |
| R5 | **One action = one database transaction.** Any error rolls back everything. | A branch move can't be left half done. |
| R6 | **Protected targets.** Never change: yourself, users in `base.group_system` or `base.group_erp_manager`, portal or public users, or users outside your own branches. | Prevents locking yourself out and climbing up to admin rights. |
| R7 | **Signed, short-lived, non-replayable requests.** Requests are signed with HMAC-SHA256, valid for 120 s, and each `request_id` is accepted only once. | A captured request can't be sent again. |
| R8 | **Writes off by default.** Enabled per company in Settings. Users also need a dedicated group. | The client decides whether to use the feature and who gets it. |
| R9 | **Full audit log** of every preview and every write, readable by the client's admins. | Accountability. |
| R10 | **No deleting.** Deactivate only; reactivating is also an action. | Every change can be undone. |

## 3. Prerequisite (the client must confirm this)

Because there is no `sudo()`, the manager's own Odoo user must already hold the rights for each change:

| Change | Odoo right the manager needs |
|---|---|
| Edit another user's groups, allowed branches, or active flag | **Administration → Access Rights** (`base.group_erp_manager`) |
| Edit a POS's Allowed Employees | **Point of Sale → Administrator** (`point_of_sale.group_pos_manager`) |
| Read employees for POS assignment | provided by the POS manager rights through `pos_hr` |

Today, Ahmed Fadl does Scenarios 1 and 2 by hand, so he very likely has these already. If a client does **not** want managers to have "Access Rights", Option B can't do the job without `sudo()`. That would be a separate, higher-risk design that needs its own approval: a "delegated admin" with explicit checks. We are **not** proposing it here.

## 4. Architecture

```
Manager (Vita Bot chat)
  │  "Move Mohamed Elsayed to Wadi Jaleel 3"
  ▼
Vita Bot backend ── AI picks action + parameters
  │  1. POST /vita_bot/api/v1/action   dry_run=true   (signed)
  ▼
Odoo addon ── runs AS the manager, checks access, returns preview (writes nothing)
  ▲
  │  Vita Bot shows a Confirm card with the preview
  │  Manager clicks Confirm
  │  2. POST same action, same request_id, dry_run=false (signed)
  ▼
Odoo addon ── writes AS the manager in one transaction, writes the audit log
```

- Reading data for normal Ask Odoo answers stays on the existing XML-RPC integration user. That user **stays read-only** and gets no write rights.
- Vita Bot already knows each person's `odoo_user_id` from SSO sign-in (client key + Odoo user id).

## 5. What the Odoo team builds

### 5.1 Endpoint

```
POST /vita_bot/api/v1/action
@http.route(..., type="json", auth="none", methods=["POST"], csrf=False)
```

Headers:

- `X-VitaBot-Timestamp`: Unix seconds
- `X-VitaBot-Signature`: `hex(HMAC_SHA256(secret, timestamp + "\n" + raw_request_body))`

Body (`params` of the JSON-RPC call):

```json
{
  "request_id": "6f1c...uuid",
  "actor_odoo_user_id": 42,
  "action": "relocate_user",
  "dry_run": true,
  "params": { "user_id": 57, "from_branch_id": 3, "to_branch_id": 5 }
}
```

Response:

```json
{ "ok": true,  "dry_run": true, "preview": { "changes": [...], "warnings": [...] } }
{ "ok": true,  "dry_run": false, "result": { "changes": [...] }, "log_id": 812 }
{ "ok": false, "error": { "code": "access_denied", "message": "..." } }
```

Request flow, in order (stop at the first failure):

1. Read the secret (see §5.3). If it is missing → `not_configured`.
2. Check the timestamp is within ±120 s → `expired`. Verify the signature with `hmac.compare_digest` → `bad_signature`. Log both to the server log only; there is no user context yet.
3. Build the environment **as the actor, without sudo**:
   ```python
   env = api.Environment(request.cr, actor_id, {"lang": ..., "tz": ...})  # su=False by default
   actor = env.user
   ```
4. Check the actor: `actor.exists()`, `actor.active`, not `actor.share`, `actor.has_group("cpbot_vita_bot_link.group_vita_bot_admin_actions")` → `actor_not_allowed`.
5. Set `allowed_company_ids = actor.company_ids.ids` in the context.
6. Check writes are enabled for this company (§5.3) → `writes_disabled`. This applies to write actions only.
7. Replay check: if a log row with this `request_id` and `dry_run=false` already exists → return that stored result (`replayed: true`) and do nothing.
8. Look up the handler in a fixed `ACTIONS = {...}` dict → `unknown_action`.
9. Run the handler. Map errors to codes: `AccessError` → `access_denied`, `UserError` / `ValidationError` → `validation_error`, anything else → `internal_error`, after logging the details server-side.
10. Write the audit log row (§5.4) in the same transaction.

### 5.2 Actions

All IDs are Odoo record IDs. Vita Bot resolves names to IDs with the read actions first. "Branch" means `res.company`; **if your build uses a custom branch model or field, tell us and swap it in.**

#### Read actions (no confirm needed; still run as the actor, so they only see what the actor can see)

| Action | Params | Returns |
|---|---|---|
| `find_users` | `query` (Arabic or English name, login or email), `branch_id?` | List of `{id, name, login, active, branches}`. **Must return all matches.** "محمد" matches both Mohamed Elsayed and Mohamed Adel, and Vita Bot will ask which one. |
| `get_user_access` | `user_id` | Branches (allowed + default), POS configs where they are an Allowed Employee, allowlisted groups they have, `active`. |
| `who_has_permission` | `permission_key`, `branch_id?` | Users holding that allowlisted group, optionally only those in a branch. |
| `list_branches` | none | Branches visible to the actor. |
| `list_pos_configs` | `branch_id?` | `{id, name, branch, allowed_employees, restrict_price_control}`. |

#### Write actions (always `dry_run: true` first, then confirm)

| Action | Params | What it does |
|---|---|---|
| `set_user_branches` | `user_id`, `add_branch_ids[]`, `remove_branch_ids[]`, `default_branch_id?` | Edits `company_ids`. If the default company is removed, `default_branch_id` is required (Odoo needs `company_id ∈ company_ids`). |
| `set_pos_employees` | `pos_config_id`, `add_user_ids[]`, `remove_user_ids[]` | Edits `pos.config.employee_ids` using each user's linked `hr.employee`. |
| `relocate_user` | `user_id`, `from_branch_id`, `to_branch_id`, `pos_config_ids[]?`, `remove_from_old_pos: true` | **Scenario 1 in one transaction:** branch change + default branch + moving the employee's company if needed + POS Allowed Employees in the new branch + removal from the old branch's POS. |
| `set_user_permissions` | `user_id`, `add[]`, `remove[]` (permission keys) | Adds or removes **allowlisted groups only**. |
| `set_user_active` | `user_id`, `active` (bool), `reason` | Deactivates or reactivates. On deactivate, also removes the user from all POS Allowed Employees. Optionally archives the linked employee (Settings option, off by default). |

#### Rules every write handler must enforce (on top of Odoo's own checks)

- `user_id != actor.id` → `self_change_forbidden`
- The target is not in `base.group_system` or `base.group_erp_manager` → `protected_user`
- The target is an internal user (not `share`) → `protected_user`
- The target shares at least one branch with the actor, and every branch in the request is one of the actor's branches → `out_of_scope`
- Every permission key is in the allowlist → `not_in_allowlist`
- Never write `groups_id` with a full replace (`(6, 0, ids)`). Only add `(4, id)` and remove `(3, id)` for the specific allowlisted groups, so groups the bot doesn't manage are never touched.
- Before writing, call `check_access_rights("write")` and `check_access_rule("write")` on the target records. This lets the **preview** report `access_denied` instead of only the confirm step failing.

### 5.3 Settings, groups and secret (all without sudo)

| Item | Implementation | Note on sudo |
|---|---|---|
| **Action secret** | Read from the **Odoo server config** (`odoo.tools.config.get("vita_bot_action_secret")`), not from `ir.config_parameter`. Use a different value per client, separate from the SSO secret. | Reading `ir.config_parameter` as a normal user would need sudo; the server config does not. It also keeps the secret out of the database and the UI. |
| **Writes enabled** | A boolean on `res.company` (`vita_bot_writes_enabled`, default False), shown on the Vita Bot settings page. | The actor can read their own company. |
| **Allowed group** | New `res.groups`: `cpbot_vita_bot_link.group_vita_bot_admin_actions` ("Vita Bot: can manage users"). | Assigned by the client admin by hand. |
| **Permission allowlist** | New model `vita.bot.permission` with fields `key`, `label_en`, `label_ar`, `group_id`, `active`. Readable by the allowed group, editable by `base.group_system` only. Seed with the POS keys in §6. | Readable without sudo through `ir.model.access.csv`. |

### 5.4 Audit log

New model `vita.bot.action.log`:

`request_id` (unique, indexed), `actor_id`, `action`, `dry_run`, `params` (JSON), `target_user_id`, `changes` (JSON: before and after), `state` (`ok` / `error`), `error_code`, `create_date`.

- `ir.model.access.csv`: the allowed group gets **create + read**, with no write and no unlink. `base.group_system` gets read.
- Record rule: users of the allowed group read **only their own** rows. Admins read all.
- Menu: Settings → Technical → Vita Bot → Action Log (admins only), read-only views.
- Because the actor has create rights, logging works **without sudo**.

Optional: also post a short note on the target's linked `hr.employee`, if one exists, e.g. "Allowed branches changed via Vita Bot by Ahmed Fadl".

### 5.5 Module housekeeping

- `depends`: add `mail`. **Do not** hard-depend on `point_of_sale`, `pos_hr` or `hr`. Check at runtime (`"pos.config" in env`) and return `not_available`, so the addon still installs on clients without POS.
- Version `15.0.1.1.0`. Test the zip on **Python 3.9**. Keep `from __future__ import annotations` as in `sso.py`.
- Wrap every handler so an error can never affect the rest of Odoo, the same pattern as the existing SSO controller.

## 6. Permission keys (initial allowlist; the Odoo team confirms the XML IDs)

| Key | Label (EN / AR) | Odoo group | Note |
|---|---|---|---|
| `pos_user` | POS User / مستخدم نقطة البيع | `point_of_sale.group_pos_user` | |
| `pos_admin` | POS Administrator / مدير نقطة البيع | `point_of_sale.group_pos_manager` | In the UI this is one selection (User / Administrator). Removing `pos_admin` must **keep** `pos_user`. |
| `pos_price_edit` | Product Price Editing / تعديل أسعار المنتجات | **To be confirmed** | Standard Odoo 15 has no per-user price-editing checkbox; see §8 Scenario 2. |

## 7. Vita Bot side (for context; our team builds this)

- New tools for the AI. Write tools never call Odoo for real: they only request a **preview**.
- Vita Bot shows a Confirm card with the preview in Arabic and English. Only the actor can confirm it, and it expires after 5 minutes.
- On Confirm, Vita Bot sends the same `request_id` with `dry_run: false`.
- If a name matches more than one user, the bot always asks which one. It never picks one.
- The secret is stored encrypted per client in `odoo_client_connections`.

## 8. Scenarios

**People:** Pharmacy Manager **Ahmed Fadl (احمد فضل)**. Staff: **Mohamed Elsayed (محمد السيد)** at Al-Mujahideen 1, and **Mohamed Adel (محمد عادل)** at Wadi Jaleel 3.

### Scenario 1: User branch relocation

> Ahmed: "انقل محمد السيد من المجاهدين 1 إلى وادي جليل 3" (Move Mohamed Elsayed from Al-Mujahideen 1 to Wadi Jaleel 3)

| Step | Call | Expected |
|---|---|---|
| 1 | `find_users("محمد السيد")` | Exactly one match → Mohamed Elsayed. (If the request were only "محمد", it returns 2 matches and the bot asks which one.) |
| 2 | `list_pos_configs(branch_id=Wadi Jaleel 3)` | The branch's POS configs. If there is more than one, the bot asks which POS. |
| 3 | `relocate_user(dry_run=true)` | Preview: remove branch Al-Mujahideen 1, add Wadi Jaleel 3, set the default branch to Wadi Jaleel 3, move the employee record's company if needed, add him to POS "Wadi Jaleel 3" Allowed Employees, remove him from Al-Mujahideen 1's POS. |
| 4 | Ahmed confirms → `relocate_user(dry_run=false)` | All changes in **one transaction**, one audit row. |

The Odoo team must handle these:

- **Allowed Employees semantics.** In `pos_hr`, an empty `employee_ids` means **all employees are allowed**. Adding Mohamed to an empty list would **lock everyone else out**. The preview must show a warning in that case, and the handler must not proceed unless the request explicitly confirms it.
- The user must have a linked `hr.employee` (`user_id`). If not → `validation_error` "no employee record". Do not create one automatically.
- If Mohamed has an **open POS session** at Al-Mujahideen 1 → warn in the preview. Do not close it: closing a session posts accounting entries.
- Fails with `out_of_scope` if Ahmed is not himself allowed on Wadi Jaleel 3.

### Scenario 2: Remove price editing (manager approval only)

> Ahmed: "شيل صلاحية تعديل الأسعار من محمد السيد في نقطة البيع" (Remove Mohamed Elsayed's price-editing permission in the POS)

| Step | Call | Expected |
|---|---|---|
| 1 | `get_user_access(Mohamed Elsayed)` | Shows that he has `pos_admin` (and `pos_price_edit` if it exists). |
| 2 | `set_user_permissions(remove=["pos_admin","pos_price_edit"], dry_run=true)` | Preview: POS rights go from Administrator to User, and Price Editing is removed. `pos_user` is kept. |
| 3 | Ahmed confirms → `dry_run=false` | Groups updated, audit row written. |
| 4 | Bot reply | "Done. Ask Mohamed to close and reopen the POS (log out and back in) for the change to take effect." |

The Odoo team must confirm:

- **What "Product Price Editing" is on the client's Odoo.** In standard Odoo 15, price changes are controlled per POS by `pos.config.restrict_price_control` ("Restrict Price Modifications to Managers"): with it on, only POS Administrators can change prices. Removing `pos_admin` is then enough. If the client has a **custom group** for price editing, send us its XML ID and we add it as `pos_price_edit`.
- The preview should **warn if `restrict_price_control` is off** on Wadi Jaleel 3's POS, because then removing Administrator does **not** stop price edits. Changing that POS setting would be a separate, explicit action (`set_pos_price_control`) if wanted.
- **Refreshing the POS session:** the bot does **not** close or reload sessions. The POS screen keeps the user's rights from when it was loaded, so the cashier must reload. If Mohamed has an open session, the preview lists it so Ahmed knows to tell him.

### Scenario 3: Deactivate a user

> Ahmed: "عطّل حساب محمد عادل" (Deactivate Mohamed Adel's account)

1. `find_users` → Mohamed Adel.
2. `set_user_active(active=false, dry_run=true)` → Preview: login disabled, removed from POS Allowed Employees of Wadi Jaleel 3, plus a warning if he has an open POS session.
3. Confirm → applied. It can be undone with `set_user_active(active=true)`, but POS assignments are **not** restored automatically. The preview of the reactivation says so.

### Scenario 4: Ask about permissions

> "مين يقدر يعدل الأسعار في وادي جليل 3؟" (Who can edit prices at Wadi Jaleel 3?)

`who_has_permission("pos_admin", branch_id=Wadi Jaleel 3)`, plus the POS `restrict_price_control` value, gives a plain answer with names. This is read-only and needs no confirm.

### Negative tests (must all be refused)

| Case | Expected code |
|---|---|
| Ahmed tries to change his own permissions | `self_change_forbidden` |
| Ahmed tries to deactivate a user in `base.group_system` | `protected_user` |
| Request to add `base.group_system` or any group not on the allowlist | `not_in_allowlist` |
| Target user only in a branch Ahmed doesn't belong to | `out_of_scope` |
| Actor without the "Vita Bot: can manage users" group | `actor_not_allowed` |
| Actor without Access Rights in Odoo | `access_denied` (from Odoo itself) |
| Writes disabled for the company | `writes_disabled` |
| Same `request_id` sent twice | Second call returns the first result, `replayed: true`, no second write |
| Timestamp 10 minutes old, or wrong signature | `expired` / `bad_signature` |
| Error in the middle of `relocate_user` | Nothing changed (full rollback) |

## 9. Open questions for the Odoo team

1. Are branches `res.company` (multi-company), or a custom branch model or field? Give the technical field name for "Allowed Branches".
2. Is "Product Price Editing" a custom group? If so, what is its XML ID? If not, is `restrict_price_control` on for every branch POS?
3. Do all staff users have a linked `hr.employee`? Is `pos_hr` installed on every client?
4. Do Pharmacy Managers already have **Administration → Access Rights**? (Required; see §3.)
5. Can we set `vita_bot_action_secret` in each client's Odoo server config, or do you need another way to store it without sudo?
6. Can Vita Bot's server reach `https://<client>.vitacareonline.com/vita_bot/api/v1/action`? Any firewall or reverse-proxy rule needed? We suggest allowing that path only from Vita Bot's IP.
7. When a user is deactivated, should the linked employee also be archived by default?

## 10. Deliverables

1. `cpbot_vita_bot_link` `15.0.1.1.0`: the endpoint, actions, rules, settings, allowlist model, audit log, security files and views.
2. Seed data: the allowlist entries from §6 (inactive until the client admin turns them on).
3. Tests (`odoo.tests.TransactionCase`) covering §8, including every negative test.
4. Installable zip, tested on Odoo 15 / Python 3.9.
5. A short install note for client admins: the server config key, turning writes on, and assigning the group.
