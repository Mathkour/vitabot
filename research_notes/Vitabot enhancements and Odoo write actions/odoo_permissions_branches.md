# Odoo security/permission model for an external AI chatbot performing a write: changing another user's allowed branches (companies), Odoo 16-19

Method note: most findings come from reading the Odoo source for branches 16.0, 17.0, 18.0 and 19.0 (downloaded from raw.githubusercontent.com on 2026-11-10, with line numbers quoted), plus the official docs. Line numbers refer to those branch heads and can drift slightly in later point releases. Local context: the repo's addon `cpbot_vita_bot_link/__manifest__.py` declares `'version': '15.0.1.0.9'`, so at least one target Odoo instance may be **Odoo 15**. Odoo 15 was not researched (see Gaps).

## 1. What "branches" are, and how they relate to res.users.company_ids / company_id (16 vs 17/18/19)

### Takeaway
A branch is just a `res.company` record whose `parent_id` points to another company. Odoo 16 already had `parent_id`/`child_ids` ("Child Companies"). Odoo 17 turned this into the real "Branches" feature: a `parent_path` hierarchy, `root_id`, fields delegated from the root company, a hierarchy that cannot be changed later, and company-switcher behaviour. A user's access to a branch works exactly like access to any company: the branch must be in `res.users.company_ids` (allowed companies), and `company_id` (the default company) must be one of them.

### Cited Findings
- **Odoo 16:** `parent_id = fields.Many2one('res.company', string='Parent Company', index=True)` and `child_ids = fields.One2many('res.company', 'parent_id', string='Child Companies')`. There is only a recursion check: "You cannot create recursive companies." — [res_company.py 16.0 L63-64, L288-290](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_company.py#L63)
- **Odoo 17:** `child_ids` is relabelled `string='Branches'`. New fields: `all_child_ids`, `parent_ids` (computed from `parent_path`) and `root_id` (`company.root_id = company.parent_ids[0]`). — [res_company.py 17.0 L34-39, L109-112](https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/res_company.py#L34)
- **Odoo 17+:** `write()` raises `UserError("The company hierarchy cannot be changed.")` if `'parent_id' in values`. Unlinking a company that has branches raises "Companies that have associated branches cannot be deleted. Consider archiving them instead." Archiving a company also archives its branches. — [res_company.py 17.0 L288, L299-309, L322](https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/res_company.py#L299); same in [18.0 L351-367](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_company.py#L351) and [19.0 L359-361](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_company.py#L359)
- **Odoo 18/19:** `parent_id` gains `ondelete='restrict'`. — [res_company.py 18.0 L37](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_company.py#L37), [19.0 L51](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_company.py#L51)
- **Delegated fields (17+):** these must be identical on every branch. They are copied from the root company and shown read-only. In base the list is `['currency_id']`; other modules (e.g. accounting) extend it. — [res_company.py 18.0 L96-104](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_company.py#L96)
- **`_accessible_branches()` (17+):** it walks down `child_ids` and keeps only branches in `self.env.companies`. In other words, the branches a user can actually use are the intersection of the hierarchy with the companies the user has active/allowed. — [res_company.py 18.0 L444-464](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_company.py#L444)
- **User docs (18):** branches are created from the parent company form's **Branches** tab. Quotes:
  - "Always create the parent company first."
  - A parent company "cannot be converted into a branch later."
  - "Independent subsidiaries should be created as additional companies, not branches."
  - "User access can be granted or restricted at the parent company level, the branch level, or both."
  - "Selecting the parent company automatically links all its branches, while selecting a branch connects to that branch only." (this is company-switcher behaviour)
  - Source: [Odoo 18 docs: Companies](https://www.odoo.com/documentation/18.0/applications/general/companies.html)
- **res.users fields (identical in 16-19):**
  - `company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company.id, help='The default company for this user.', context={'user_preference': True})`
  - `company_ids = fields.Many2many('res.company', 'res_company_users_rel', 'user_id', 'cid', string='Companies', default=lambda self: self.env.company.ids)`
  - Neither field has a `groups=` restriction.
  - Sources: [res_users.py 18.0 L401-404](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L401), [19.0 L245-248](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L245)
- **Constraint:** `@api.constrains('company_id', 'company_ids', 'active')` raises `ValidationError('Company %(company_name)s is not in the allowed companies for user %(user_name)s (%(company_allowed)s).')` for an active user whose `company_id not in company_ids`. The method is named `_check_company` in 16/17/18 and was renamed `_check_user_company` in 19. — [res_users.py 16.0 L544](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L544), [18.0 L589](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L589), [19.0 L498-506](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L498)
- **Automatic multi-company group (all versions):** when `company_ids` is written or created, Odoo links `base.group_multi_company` if the user has more than one company and unlinks it if the user has one or none. — [res_users.py 16.0 L1703-1724](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L1703), [19.0 L1358-1396](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L1358)
- **Odoo 19 rename:** `groups_id` became `group_ids` ("Groups explicitly assigned to the user"). A new `all_group_ids` holds groups plus implied groups. There is also a new `role` selection (`group_user` / `group_system`) that sets admin vs. user. — [res_users.py 19.0 L257-258, L272](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L257)

### Inferences
- "Allow user X on branch Y" means `company_ids` gets `Command.link(Y)`. "Disallow" means `Command.unlink(Y)`, which fails if Y is also X's `company_id`.
- Granting the parent company does **not** automatically put its branches in `company_ids`. The "parent selects branches" behaviour exists only in the company switcher, and only for branches already in the user's allowed list (`_accessible_branches` intersects with `env.companies`). A tool for "give access to the whole group" must therefore link every branch explicitly, e.g. `env['res.company'].search([('id', 'child_of', parent.id)])`.
- Any integration must use `groups_id` on 16-18 and `group_ids` on 19.

### Gaps
- I did not check whether Odoo 17+ add-on modules (e.g. `account`) add extra branch-specific checks on user access. Base has none.
- Odoo 15 behaviour was not checked (the addon manifest says 15.0). Branches as a feature do not exist before 17. In 15/16, `parent_id` is a plain hierarchy with no delegated fields.

## 2. Which groups can edit another user's company_ids, and can a restricted admin grant companies they lack?

### Takeaway
Writing `res.users` requires **`base.group_erp_manager` ("Access Rights")**. `base.group_system` ("Settings") implies it. Regular internal users (`base.group_user`) have read-only ACLs on res.users. When they "write themselves", only `SELF_WRITEABLE_FIELDS` is allowed, and `company_ids` is not in that list. Odoo has **no built-in check** that stops an Access Rights user from granting a company that is not in their own `company_ids`. A record rule even gives `group_erp_manager` read access to **all** companies. Any "can only grant branches you have yourself" policy has to be custom.

### Cited Findings
- **ACLs (`ir.model.access.csv`, 18):**
  - `access_res_users_group_erp_manager` → `model_res_users`, `group_erp_manager`, perms `1,1,1,1`
  - `access_res_users_employee` (`base.group_user`), `access_res_users_portal` and `access_res_users_public` → `1,0,0,0` (read only)
  - `access_res_company_group_erp_manager` → `1,1,1,1`; employee/portal/public → read only
  - The 16-19 files carry the same erp_manager rows.
  - Source: [ir.model.access.csv 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/ir.model.access.csv)
- **Group hierarchy:** `group_erp_manager` is named "Access Rights" and implies `group_user`. `group_system` is named "Settings" and implies `group_erp_manager` and `group_sanitize_override`. — [base_groups.xml 18.0 L10-23](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/base_groups.xml#L10)
- **Record rules on res.company (16-19):**
  - `res_company_rule_employee`, `res_company_rule_portal` and `res_company_rule_public` all use `[('id','in', company_ids)]`. Normal users only see their own allowed companies.
  - `res_company_rule_erp_manager` (`group_erp_manager`) uses `[(1,'=',1)]`. Access Rights managers see **every** company.
  - Group rules are OR-ed, so an erp_manager can read and link any company.
  - Sources: [base_security.xml 16.0 L146-173](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/security/base_security.xml#L146), [18.0 L112-139](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/base_security.xml#L112), [19.0 L105-132](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/security/base_security.xml#L105)
- **Record rule on res.users (global, 16-19):** `res_users_rule` uses `['|', ('share', '=', False), ('company_ids', 'in', company_ids)]`. Internal (non-share) users are visible to everyone. Share/portal users are visible only when they share a company with the current user. Odoo 19 adds `res_users_rule_portal` (portal users only see users of their own commercial partner). — [base_security.xml 18.0 L148-153](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/base_security.xml#L148), [19.0 L141-153](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/security/base_security.xml#L141)
- **How rules combine:** "if two global rules apply then both must be satisfied", while "if two group rules apply then either can be satisfied". Global and group rulesets intersect. — [Odoo 18 docs: Security in Odoo](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)
- **Self-write path in `res.users.write` (18):**
  - If `self == self.env.user` and every key is in `SELF_WRITEABLE_FIELDS` (or starts with `context_`), Odoo drops `company_id` when it is not in `self.env.user.company_ids.ids` and then writes with `self.sudo()`.
  - Otherwise the write goes through normal ACLs.
  - Other guards: "You cannot activate the superuser." and "You cannot deactivate the user you're currently logged in as."
  - Source: [res_users.py 18.0 L730-750](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L730)
- **Writable-by-self fields (18):** `SELF_WRITEABLE_FIELDS` = `['signature', 'action_id', 'company_id', 'email', 'name', 'image_1920', 'lang', 'tz']`. `company_ids` is **not** included. — [res_users.py 18.0 L356](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L356)
- **Cache reset after company changes (18):** after a `company_id`/`company_ids` change, `write()` resets lazy `env.company`/`env.companies` and `env._cache_key` on every env of the affected user in the transaction. After a groups change, it calls `ir.model.access.call_cache_clearing_methods()`. — [res_users.py 18.0 L767-785](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L767)
- **Admin helpers:** `_is_admin()` returns `self._is_superuser() or self.sudo().has_group('base.group_erp_manager')`. `_is_system()` returns `self.sudo().has_group('base.group_system')`. — [res_users.py 18.0 L1300-1306](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L1300)

### Inferences
- **No "can only grant what you hold" check (inference from source):** I found no base code that compares the companies being linked with the writer's own `company_ids`. Many2many link commands do not check access on the target company. The erp_manager rule makes every company readable anyway.
- **Escalation risk:** Access Rights can also write `groups_id`/`group_ids`. The source I read has no guard that stops an erp_manager from adding `base.group_system` to someone, including themselves. I did not verify this exhaustively.
- **Consequences for the chatbot:**
  - Expose **only** `company_ids` mutations, never generic `write` on res.users.
  - Add custom policy checks, e.g. the actor must have the target branch (or its root) in their own `company_ids`, and the target user must share a company with the actor.

### Gaps
- I found no official doc page that explicitly states "an admin can grant companies they don't belong to". The conclusion is inferred from ACLs and rules.
- I did not check whether any Enterprise module adds restrictions.

## 3. Checking permissions programmatically, and what is callable over RPC

### Takeaway
- **16/17:** use `check_access_rights(op, raise_exception=False)` (model ACL) and `check_access_rule(op)` (record rules). Both are public and RPC-callable.
- **18:** these are replaced by `check_access(op)` / `has_access(op)` / `_filtered_access(op)`. The old names still exist but emit `DeprecationWarning`.
- **19:** `check_access` is marked `@api.private` (not RPC-callable, "use has_access"). `has_access` stays public.
- Group checks: `res.users.has_group(xmlid)`. In 18+ it raises when a non-internal caller checks another user. `user_has_groups` was removed in 18 in favour of `env.user.has_groups(spec)`.
- Over RPC, any method whose name starts with `_` or that carries `@api.private` is rejected.

### Cited Findings
- **16/17 methods:**
  - `@api.model def check_access_rights(self, operation, raise_exception=True)` (public)
  - `def check_access_rule(self, operation)` (public)
  - `def _filter_access_rules(self, operation)` (private)
  - `def check_field_access_rights(self, operation, fields)`
  - Sources: [models.py 16.0 L3522-3570](https://github.com/odoo/odoo/blob/16.0/odoo/models.py#L3522), [17.0 L4155-4203](https://github.com/odoo/odoo/blob/17.0/odoo/models.py#L4155)
- **18 methods:**
  - `def check_access(self, operation: str) -> None` (raises `AccessError`). Its docstring says "when ``self`` is empty, the method checks whether the current user has some permission to perform ``operation`` on the model in general", e.g. `records.browse().check_access(operation)`.
  - `def has_access(self, operation: str) -> bool` ("fully consistent with method check_access but returns a boolean").
  - `def _filtered_access(self, operation)`.
  - `_check_access` returns `None` or a `(forbidden_records, exc_factory)` pair. It first checks the `ir.model.access` ACL, then `ir.rule._compute_domain` against `self.sudo().filtered_domain(domain)`. Both checks are skipped when `env.su` is set.
  - `check_access_rights` warns "check_access_rights() is deprecated since 18.0; use check_access() instead." `check_access_rule` and `_filter_access_rules` carry the same kind of warning.
  - Source: [models.py 18.0 L4442-4540](https://github.com/odoo/odoo/blob/18.0/odoo/models.py#L4442)
- **19 location and decorators:** the ORM moved to `odoo/orm/models.py`. `@api.private  # use has_access` decorates `check_access`. `has_access` is public. `check_access_rights` (`@api.model`) and `check_access_rule` still exist, decorated with `@api.deprecated("... deprecated since 18.0 ...")`. — [odoo/orm/models.py 19.0 ~L4105-4198](https://github.com/odoo/odoo/blob/19.0/odoo/orm/models.py#L4105)
- **RPC filter (16-19):** `get_public_method()` in `odoo/service/model.py` raises `AccessError(f"Private methods (such as '{model._name}.{name}') cannot be called remotely.")` when `name.startswith('_')`, when the method has `_api_private`, or when the name is in `_UNSAFE_ATTRIBUTES`. The `@api.private` decorator exists in 16.0+ (`method._api_private = True`). — [service/model.py 16.0 L27-43](https://github.com/odoo/odoo/blob/16.0/odoo/service/model.py#L27), [18.0 L29-45](https://github.com/odoo/odoo/blob/18.0/odoo/service/model.py#L29), [19.0 L45-77](https://github.com/odoo/odoo/blob/19.0/odoo/service/model.py#L45); [api.py 16.0 L384-397](https://github.com/odoo/odoo/blob/16.0/odoo/api.py#L384)
- **`has_group` in 16/17:** `@api.model def has_group(self, group_ext_id)` switches to `with_user(self.id)` when called on another user's record and then calls `_has_group`. There is **no** restriction, so any authenticated RPC user can check any user's groups. — [res_users.py 16.0 L1055-1062](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L1055), [17.0 L1088-1095](https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/res_users.py#L1088)
- **`has_group` in 18/19:**
  - `@api.readonly def has_group(self, group_ext_id: str) -> bool` with `ensure_one()`.
  - It raises `AccessError("You can ony call user.has_group() with your current user.")` [sic] unless `env.su`, `self == env.user`, or the caller is in `base.group_user`.
  - `base.group_no_one` returns True only in debug mode.
  - New `has_groups(group_spec)` accepts comma-separated specs with `!` negation, e.g. `"base.group_user,base.group_portal,!base.group_system"`.
  - Sources: [res_users.py 18.0 L1159-1210](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L1159), [19.0 L1034-1085](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L1034)
- **`user_has_groups`:** `BaseModel.user_has_groups(groups)` exists in 16.0 (L1472) and 17.0 (L1559). It no longer exists in `models.py` 18.0/19.0. — [models.py 17.0 L1559](https://github.com/odoo/odoo/blob/17.0/odoo/models.py#L1559)
- **Field access (`groups=` attribute):** restricted fields are removed from views and `fields_get()`, and "attempts to (explicitly) read from or write to restricted fields results in an access error". — [Odoo 18 docs: Security in Odoo](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)
- **Public methods are attack surface:** "Any public method can be executed via a RPC call with the chosen parameters". Underscore methods are not callable from buttons or the external API. — [Odoo 18 docs: Security pitfalls](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)
- **Company context validation (`env.company`/`env.companies`, 18/19):** if the `allowed_company_ids` context contains IDs outside `self.user._get_company_ids()` (active companies the user belongs to) and not su, Odoo raises `AccessError("Access to unauthorized or invalid companies.")`. — [api.py 18.0 L698-751](https://github.com/odoo/odoo/blob/18.0/odoo/api.py#L698), [orm/environments.py 19.0 L219-252](https://github.com/odoo/odoo/blob/19.0/odoo/orm/environments.py#L219)

### Inferences
- **Version-portable "may actor write user X?" check over RPC, authenticated as the actor:**
  - 16/17: `execute_kw(db, uid, key, 'res.users', 'check_access_rights', ['write'], {'raise_exception': False})`, then `check_access_rule` on `[X]` (it raises instead of returning).
  - 18: same calls, with deprecation warnings.
  - 19: `has_access` on ids `[X]` with `operation='write'`. `check_access` is private.
  - None of these tell you whether a specific *company* may be granted. That is a business policy (see section 2), so a custom endpoint is the right place for it.
- **Do not rely on the service account's own checks:** `has_access`/`check_access` evaluated under a service account or `sudo()` always return True or skip checks (`env.su`). The check must run as the end user's uid (`with_user(actor)` or the actor's own credentials).

### Gaps
- I did not verify whether `has_access` in 18.0 is RPC-public (no `@api.private` seen next to it, so presumably yes).
- I did not exhaustively verify the exact 19.0 `has_group` RPC behaviour beyond the code shown.

## 4. External API changes in 18/19: JSON-2, deprecation of XML-RPC/JSON-RPC, API keys

### Takeaway
- Odoo 19 adds the JSON-2 API: `POST /json/2/<model>/<method>` with `Authorization: bearer <api_key>`, named args only, and one transaction per call. It runs as the key's user under normal ACLs and record rules, and uses the same public-method filter.
- `/xmlrpc`, `/xmlrpc/2` and `/jsonrpc` are scheduled for removal in **Odoo 22 (fall 2028) / Odoo Online 21.1 (winter 2027)**.
- `auth='bearer'` for custom controllers already exists in **18.0** (not 16/17).
- API keys: 18+ requires an expiration date for non-system users, capped by the group's `api_key_duration` (docs: at most three months). Keys can be scoped (`rpc` = generic bearer scope).

### Cited Findings
- **JSON-2 request format (19 docs):**
  - `POST /json/2/<model>/<method>`
  - Headers: `Authorization: bearer <key>` and `Content-Type: application/json`. `X-Odoo-Database` is optional and needed when dbfilter can't use the Host header.
  - Body: `ids`, optional `context`, and the method's parameters as named fields. "there is no way in JSON-2 to call a function with positional arguments."
  - Source: [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **JSON-2 transactions:** each call runs in its own SQL transaction, committed on success. "Using the JSON-2 API, it is not possible to chain multiple calls inside a single transaction." — [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **JSON-2 security and accounts:** calls follow the access rights, record rules and field access of the key's user. Personal accounts suit interactive use. Dedicated **bot users** "with minimal permissions and an empty password" are recommended for automated integrations. — [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **Plan requirement:** external API access is "only available on _Custom_ Odoo pricing plans". — [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **Deprecation:** XML-RPC/JSON-RPC endpoints are "scheduled for removal in Odoo 22 (fall 2028) / Odoo Online 21.1 (winter 2027)". Other `@route(type='jsonrpc')` controllers are not affected. — [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **JSON-2 controller code:** the controller lives in the new `rpc` addon (`addons/rpc/controllers/json2.py`; no such addon in 16/17/18). It is a route with `auth='bearer'` that:
  - builds `request.env[__model__].with_context(context)`,
  - resolves `get_public_method(Model, __method__)` (so private and `@api.private` methods are blocked),
  - rejects `ids` for `@api.model` methods,
  - uses read-only transactions for methods marked `@api.readonly`.
  - Source: [rpc/controllers/json2.py 19.0](https://github.com/odoo/odoo/blob/19.0/addons/rpc/controllers/json2.py)
- **`auth='bearer'` for routes:** documented in `odoo/http.py` 18.0 as: the user is authenticated with an "Authorization" header (Bearer scheme with an API token), and "The request will be executed with the permissions of the corresponding user". If the header is missing, the request falls back to session auth like `'user'`. Implemented in `ir.http._auth_method_bearer` with a Sec-Fetch header CSRF check. It is absent from 16.0/17.0 `http.py`. In 19, bearer routes default to `save_session=False` (stateless). — [http.py 18.0 ~L709](https://github.com/odoo/odoo/blob/18.0/odoo/http.py#L709), [ir_http.py 18.0 L204](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/ir_http.py#L204), [http.py 19.0 L776-828](https://github.com/odoo/odoo/blob/19.0/odoo/http.py#L776)
- **`res.users.apikeys` model (18):**
  - Fields: `name`, `user_id`, `scope`, `create_date`, `expiration_date`.
  - `_check_credentials(*, scope, key)` matches active users with `scope IS NULL OR scope = %s` and unexpired keys, and verifies a hash.
  - `_generate(scope, name, expiration_date)` always creates the key for `self.env.user` and returns the plaintext once.
  - `_check_expiration_date`:
    - is skipped for system users;
    - otherwise raises "The API key must have an expiration date" when the date is empty;
    - caps the date at the max `api_key_duration` of the user's groups (default 1 day if 0) with "You cannot exceed %(duration)s days.";
    - in 19 it also raises "You cannot set an expiration date in the past."
  - `_gc_user_apikeys` autovacuums expired keys. `_remove` is allowed only for the key owner or a system user. Only internal users can create keys.
  - Sources: [res_users.py 18.0 (APIKeys)](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py), [res_users.py 19.0 L1580-1601](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L1580)
- **API key limits (19 docs):**
  - "it is not possible to create keys that last for more than three months".
  - Keys are 160-bit random values shown once.
  - Programmatic `res.users.apikeys.generate()` / `revoke()` takes `scope` (`rpc` = generic scope for `auth='bearer'` controllers; `null` = unscoped). By default this is limited to Settings admins and is extendable via `base.enable_programmatic_api_keys`.
  - Limit `base.programmatic_api_keys_limit` (default 10, returns 422 beyond that).
  - Source: [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **`api_key_duration`:** a field on `res.groups` ("API Keys maximum duration days"), with `CHECK(api_key_duration >= 0)`. — [res_users.py 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py)

### Inferences
- **Plan for the JSON-2 move:** a FastAPI service built on `/xmlrpc/2/object` or `/jsonrpc` today should plan to move to JSON-2 (19+) or to a custom `auth='bearer'` controller (18+) before Odoo 22 / Online 21.1.
- **Short-lived keys:** 3-month key limits mean per-user stored API keys need rotation. That argues for an addon controller that relies on Odoo's own session or SSO rather than storing per-user keys in the chatbot.
- **One transaction per call:** JSON-2 means multi-step "check then write" sequences are not atomic across calls. Server-side endpoints that do check + write in one call are safer.

### Gaps
- I found no official OAuth2 "authorization server" in Odoo core for third-party apps to obtain user-scoped tokens. Core `auth_oauth` is an OAuth *client* used for login via Google and similar providers (not re-verified in this session).
- I did not check whether JSON-2 is back-ported to 18 SaaS versions.

## 5. Identity strategy: act as the end user vs. service account + sudo

### Takeaway
Run the write **as the end user** (Odoo's request env under their uid, or `with_user(actor_uid)` without sudo) so that ACLs, record rules, constraints and `write_uid` all reflect the real actor. A service account with `sudo()` bypasses every ACL and rule (`env.su` short-circuits `check_access`/`has_access`). It also records the bot as `write_uid` and turns the chatbot into a confused-deputy escalation path. Official docs recommend dedicated low-privilege bot users only for automated integrations, not for acting on behalf of humans.

### Cited Findings
- **`sudo()` skips checks:** `check_access` and `has_access` short-circuit when `self.env.su` is set (`if not self.env.su and ...` / `return self.env.su or ...`). — [models.py 18.0 L4442-4464](https://github.com/odoo/odoo/blob/18.0/odoo/models.py#L4442)
- **Bot users:** the JSON-2 docs recommend dedicated bot users with minimal permissions for automated integrations. Operations follow "the access rights, record rules and field access of the user". — [Odoo 19 External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- **`auth='user'` routes:** the request "will be executed using the rights of the user". — [http.py 18.0 ~L707](https://github.com/odoo/odoo/blob/18.0/odoo/http.py#L707)
- **Existing local addon:** the SSO controller `/vita_bot/sso` is already declared `type="http", auth="user"` and reads `request.env.user`. — local file `C:\Work\vitabot\cpbot_vita_bot_link\controllers\sso.py` L219-236
- **No chatter on res.users:** `mail` extends res.users with `_inherit = 'res.users'` / `['res.users']` only, not `mail.thread`. Its own comment calls portal status changes "manual tracking". So changes to `company_ids` are **not** tracked in a chatter by default. Only `write_uid`/`write_date` on res.users record the last writer. — [mail/models/res_users.py 19.0 L20, L184](https://github.com/odoo/odoo/blob/19.0/addons/mail/models/res_users.py#L20), [17.0 L17](https://github.com/odoo/odoo/blob/17.0/addons/mail/models/res_users.py#L17)

### Inferences
- **Recommended pattern:**
  1. The chatbot proposes the action.
  2. The user confirms.
  3. The chatbot calls a narrow endpoint in the Odoo addon, authenticated as that user. Options: a browser session via the existing SSO link, a per-user bearer key (18+), or a signed request from the backend where the addon calls `env['res.users'].browse(actor_uid)` and does `with_user(actor)` without sudo.
  4. Odoo's own ACLs enforce `group_erp_manager`, and the addon adds the branch policy.
- **Auditing:** because res.users has no chatter tracking, the addon should log explicitly, e.g. `message_post` on the target user's `partner_id` or a custom audit model, with actor, before/after `company_ids` and chatbot conversation id.
- **Signed backend requests:** if the backend is trusted and signs requests (as the SSO flow already does with the SSO secret), the addon must still resolve the actor uid from a verified identity, never from LLM output. It must then execute `with_user(actor)` so permission checks apply.

### Gaps
- There is no official Odoo doc that directly compares "on-behalf-of" with a service account for chatbots. The recommendation is derived from the security model.

## 6. Designing a narrow addon endpoint (whitelisted action + dry-run) — code patterns

### Takeaway
Expose a single JSON route, e.g. `/vita_bot/action/user_branch_access`, with `auth='user'` (all versions) or `auth='bearer'` (18+). It takes `user_id`, `company_id`, `allow: bool` and `dry_run: bool`. It runs under `request.env` (the actor's uid), checks the actor's group and company policy, computes a preview, and on commit writes only `company_ids` with `Command.link`/`Command.unlink` (tuples `(4, id)`/`(3, id)`). It handles the default-company case explicitly.

### Cited Findings
- **Commands:** `Command.link(id)` / `Command.unlink(id)` are used by Odoo itself on many2many group fields, e.g. `user.write({'groups_id': [Command.unlink(group_multi_company_id)]})` in 16-18 and `group_ids` in 19. — [res_users.py 16.0 L1707-1710](https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/models/res_users.py#L1707), [19.0 L1363-1366](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_users.py#L1363)
- **Constraint to plan for:** unlinking the user's default company raises the `company_id not in company_ids` ValidationError (see section 1). — [res_users.py 18.0 L589-596](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L589)
- **Calling `has_group` on another user:** in 18/19 the caller must be internal or su (see section 3). Inside the addon, `request.env.user.has_group(...)` (self-check) is always allowed. — [res_users.py 18.0 L1191-1206](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L1191)

Pattern (synthesized from the cited APIs; adapt `groups_id`→`group_ids` for 19; `Command` exists in 14+):

```python
from odoo import http, Command, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError

class VitaBotActions(http.Controller):
    # 16/17: auth='user' (session via SSO); 18+: auth='bearer' also possible
    @http.route('/vita_bot/action/user_branch_access', type='json', auth='user', methods=['POST'])
    def user_branch_access(self, user_id, company_id, allow, dry_run=True):
        env = request.env                      # runs as the logged-in actor, NOT sudo
        actor = env.user
        if not actor.has_group('base.group_erp_manager'):
            raise AccessError(_("You need the 'Access Rights' role to change user companies."))
        Users = env['res.users']
        # 18+: Users.browse(user_id).check_access('write'); 16/17: check_access_rights + check_access_rule
        target = Users.browse(int(user_id)).exists()
        company = env['res.company'].browse(int(company_id)).exists()
        if not target or not company:
            raise ValidationError(_("Unknown user or branch."))
        if target.share:
            raise ValidationError(_("Portal/public users are out of scope."))
        # custom policy: actor may only grant/revoke branches they hold themselves
        if company not in actor.company_ids:
            raise AccessError(_("You can only manage branches you have access to."))
        before = target.company_ids
        if allow:
            after, cmd = before | company, [Command.link(company.id)]      # == (4, id)
            vals = {'company_ids': cmd}
        else:
            if company == target.company_id:
                remaining = before - company
                if not remaining:
                    raise ValidationError(_("Cannot remove the user's only company."))
                vals = {'company_id': remaining[0].id, 'company_ids': [Command.unlink(company.id)]}  # == (3, id)
            else:
                vals = {'company_ids': [Command.unlink(company.id)]}
            after = before - company
        preview = {'user': target.display_name,
                   'before': before.mapped('display_name'),
                   'after': after.mapped('display_name'),
                   'default_company_change': vals.get('company_id')}
        if dry_run:
            return {'dry_run': True, 'preview': preview}
        target.write(vals)                     # ACL + rules + constraints enforced as actor
        target.partner_id.message_post(body=_("Allowed companies changed by %s via Vita Bot", actor.name))
        return {'dry_run': False, 'result': preview}
```

### Inferences
- **Field order in the write:** when switching the default company, put `company_id` and `company_ids` in the same write. The `@api.constrains` check runs after the write, so the final state is what gets validated.
- **Avoid `sudo()` in the endpoint:** do not use it, even for reading. The erp_manager rule already lets the actor read all companies, and other users are blocked by the record rules, which is the desired behaviour.
- **Dry-run token:** make `dry_run=True` the default. The chatbot shows the preview and then sends the same payload with `dry_run=False` plus a confirmation token, e.g. an HMAC of the payload issued with the preview, so the LLM cannot alter parameters between preview and commit.
- **Whitelist:** never pass arbitrary `vals` from the LLM. Reject any field other than the single branch toggle.
- **JSON route type:** `type='json'` is called `'jsonrpc'` in the 19 http docs. In 19, `type='json'` routes keep working; the JSON-2 deprecation notice says custom `type='jsonrpc'` routes "aren't affected".

### Gaps
- I did not verify whether `type='json'` raises a deprecation warning in 19.0 http.py. Check before shipping.

## 7. Pitfalls

### Takeaway
Main risks:
- removing the user's default company (ValidationError);
- forgetting that branches must be granted one by one;
- stale `env.company`/`env.companies` and caches;
- unvalidated `allowed_company_ids` context (Odoo raises, but the service should not forge it);
- privilege escalation through `groups_id`/`group_ids` writes, or through `sudo()` in the endpoint;
- portal/share users (`share=True`; record rule visibility; `has_group` restrictions);
- side effects such as automatic `group_multi_company` toggling.

### Cited Findings
- **Default company removal:** an active user's `company_id` must stay in `company_ids`, otherwise a ValidationError is raised. — [res_users.py 18.0 L589](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L589)
- **Self-write silently drops values:** a self-write of `company_id` outside the user's `company_ids` is silently dropped (`del values['company_id']`). — [res_users.py 18.0 L741-747](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L741)
- **Forged company context:** an `allowed_company_ids` context with companies outside the user's active `company_ids` raises "Access to unauthorized or invalid companies." for non-su envs. — [api.py 18.0 L715-720](https://github.com/odoo/odoo/blob/18.0/odoo/api.py#L715)
- **Cache invalidation:** after a `company_ids` change, Odoo resets lazy `env.company`/`env.companies` and `_cache_key` for the affected user's envs. After a groups change, it clears the ACL caches. Record-rule domains that depend on `company_ids` are re-evaluated per env. — [res_users.py 18.0 L767-785](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L767)
- **Side effect on groups:** writing `company_ids` auto-adds or removes `base.group_multi_company`, so even a pure company change modifies the user's groups. — [res_users.py 18.0 L1907-1913](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L1907)
- **Groups writes:** writing `groups_id` triggers a cascade that applies default groups to existing internal users. `UsersImplied.write` resets demoted users with `Command.clear()`. — [res_users.py 18.0 L752-765](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L752)
- **Share users:**
  - `share` is computed: False for `base.group_user` members, True otherwise ("External user with limited access, created only for the purpose of sharing data").
  - `res_users_rule` hides share users who have no common company with the actor.
  - 18/19 `has_group` refuses non-internal callers checking others.
  - Sources: [res_users.py 18.0](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py), [base_security.xml 18.0 L148-153](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/security/base_security.xml#L148)
- **Hierarchy is fixed:** in 17+ "The company hierarchy cannot be changed." A chatbot cannot "move" a branch, only grant or revoke access. — [res_company.py 18.0 L366-367](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_company.py#L366)
- **Public methods:** "Any public method can be executed via a RPC call with the chosen parameters". Make internal helpers `_private` or `@api.private`. — [Odoo 18 docs: Security pitfalls](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)
- **API-key login:** `Users.authenticate` has a special branch for `group_system` users at login (base URL guessing). API keys of system users bypass expiration limits (`_check_expiration_date` returns early when `is_system()`). Keys of admin users can therefore be long-lived. — [res_users.py 18.0 L960-975](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/res_users.py#L960)

### Inferences
- **Treat as admin-only:** granting a branch can expose all of that branch's data under multi-company record rules (`company_id in company_ids`). The chatbot should treat it as a high-risk action that needs explicit human confirmation, and it should never let the LLM choose `user_id`/`company_id` without resolving and echoing names.
- **Archived companies:** `env.companies` uses `_get_company_ids()`, which filters `active=True`. Granting an archived branch is stored but has no effect until the branch is unarchived. The preview should flag this.
- **Odoo 19 field names:** code that writes `groups_id` will break on 19 (`group_ids`). Detect the server version (`/web/webclient/version_info` or `common.version()`) and branch accordingly.

### Gaps
- I did not check whether Odoo 19 adds `res.users` tracking (e.g. `tracking=True` on `company_ids`). The base 19 field definition shows no `tracking` attribute.
- Odoo 15 specifics are unverified (the addon is versioned 15.0.x).
