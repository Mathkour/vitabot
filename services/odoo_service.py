import os
import xmlrpc.client
from dotenv import load_dotenv

import db
from services.crypto import decrypt_value

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069").strip()
ODOO_DB = os.getenv("ODOO_DB", "").strip()
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "").strip()
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "").strip()


class OdooError(Exception):
    """Raised when Odoo can't be reached or rejects our request."""


_SENSITIVE_GROUP_CATEGORIES = {"administration", "technical", "extra rights"}


def _count_by(rows: list[dict], field: str) -> dict:
    counts: dict = {}
    for row in rows:
        key = row.get(field, "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


class OdooClient:
    """
    Wraps the connection details + authenticated uid for ONE Odoo instance.

    Vita Care has ~200 client companies, each with their own fully separate
    Odoo (own URL/DB/credentials). Every client's employee questions must
    only ever hit that client's own Odoo — never Vita Care's, never another
    client's. Before this class existed, all of this module's functions
    talked to a single Odoo via module-level ODOO_URL/DB/USERNAME/PASSWORD
    and one shared _uid_cache global, which only worked because there was
    exactly one Odoo in the picture. Making the connection+uid instance
    state instead of module state means each client gets its own isolated
    OdooClient with its own uid cache, so nothing can leak across clients
    even under concurrent requests for different companies.
    """

    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.strip()
        self.db = db.strip()
        self.username = username.strip()
        self.password = password
        self._uid_cache: int | None = None

    def _get_uid(self) -> int:
        if self._uid_cache is not None:
            return self._uid_cache

        try:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            uid = common.authenticate(self.db, self.username, self.password, {})
        except xmlrpc.client.Fault as e:
            raise OdooError(f"Odoo authentication failed: {e.faultString}") from e
        except (ConnectionRefusedError, OSError, xmlrpc.client.ProtocolError) as e:
            raise OdooError(f"Could not connect to Odoo at {self.url}: {e}") from e

        if not uid:
            raise OdooError("Odoo authentication failed: check the Odoo DB, username, and password")

        self._uid_cache = uid
        return uid

    def _execute_kw(self, model: str, method: str, args: list, kwargs: dict | None = None):
        uid = self._get_uid()
        try:
            models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
            return models.execute_kw(self.db, uid, self.password, model, method, args, kwargs or {})
        except xmlrpc.client.Fault as e:
            raise OdooError(f"Odoo request failed: {e.faultString}") from e
        except (ConnectionRefusedError, OSError, xmlrpc.client.ProtocolError) as e:
            raise OdooError(f"Could not reach Odoo at {self.url}: {e}") from e

    def get_sales_summary(self) -> dict:
        orders = self._execute_kw(
            "sale.order", "search_read", [[]],
            {"fields": ["amount_total", "partner_id", "state"]},
        )

        total_revenue = sum(o["amount_total"] for o in orders)

        customer_totals: dict[str, float] = {}
        for o in orders:
            partner_name = o["partner_id"][1] if o["partner_id"] else "Unknown"
            customer_totals[partner_name] = customer_totals.get(partner_name, 0) + o["amount_total"]

        top_customer = None
        if customer_totals:
            name, total = max(customer_totals.items(), key=lambda item: item[1])
            top_customer = {"name": name, "total": round(total, 2)}

        return {
            "total_orders": len(orders),
            "total_revenue": round(total_revenue, 2),
            "top_customer": top_customer,
            "orders_by_state": _count_by(orders, "state"),
        }

    def get_top_products(self, limit: int = 5) -> list[dict]:
        lines = self._execute_kw(
            "sale.order.line", "search_read", [[]],
            {"fields": ["product_id", "product_uom_qty", "price_subtotal"]},
        )

        product_totals: dict[str, dict] = {}
        for line in lines:
            if not line["product_id"]:
                continue
            name = line["product_id"][1]
            totals = product_totals.setdefault(name, {"qty": 0, "revenue": 0})
            totals["qty"] += line["product_uom_qty"]
            totals["revenue"] += line["price_subtotal"]

        sorted_products = sorted(product_totals.items(), key=lambda item: item[1]["revenue"], reverse=True)
        return [
            {"name": name, "qty_sold": round(data["qty"], 2), "revenue": round(data["revenue"], 2)}
            for name, data in sorted_products[:limit]
        ]

    def get_top_customers(self, limit: int = 5) -> list[dict]:
        orders = self._execute_kw(
            "sale.order", "search_read", [[]],
            {"fields": ["amount_total", "partner_id"]},
        )
        customer_totals: dict[str, float] = {}
        for o in orders:
            if not o.get("partner_id"):
                continue
            name = o["partner_id"][1]
            customer_totals[name] = customer_totals.get(name, 0) + o["amount_total"]

        sorted_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)
        return [
            {"name": name, "total_spent": round(total, 2)}
            for name, total in sorted_customers[:limit]
        ]

    def get_customer_summary(self) -> dict:
        total_customers = self._execute_kw(
            "res.partner", "search_count", [[("customer_rank", ">", 0)]],
        )
        return {"total_customers": total_customers}

    def build_odoo_context(self) -> str:
        sales = self.get_sales_summary()
        products = self.get_top_products(limit=10)
        customers = self.get_customer_summary()

        lines = []
        lines.append(f"TOTAL SALES ORDERS: {sales['total_orders']}")
        lines.append(f"Total revenue (all orders, all statuses): {sales['total_revenue']}")
        lines.append(f"total customers : {customers['total_customers']}")

        if sales["top_customer"]:
            lines.append(
                f"TOP CUSTOMER BY SPEND: {sales['top_customer']['name']} "
                f"(total: {sales['top_customer']['total']})"
            )

        lines.append("\nORDERS By status:")
        for state, count in sales["orders_by_state"].items():
            lines.append(f"-{state}:{count}")

        lines.append("\nTOP PRODUCTS BY REVENUE:")
        for p in products:
            lines.append(f"- {p['name']}: qty sold {p['qty_sold']}, revenue {p['revenue']}")

        return "\n".join(lines)

    def search_orders(
        self,
        customer_name: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        domain = []
        if customer_name:
            domain.append(("partner_id.name", "ilike", customer_name))

        if status:
            domain.append(("state", "=", status))
        if date_from:
            domain.append(("date_order", ">=", date_from))

        if date_to:
            domain.append(("date_order", "<=", date_to))

        orders = self._execute_kw(
            "sale.order", "search_read", [domain],
            {
                "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
                "limit": limit,
                "order": "date_order desc",
            },
        )
        return [
            {
                "order_number": o["name"],
                "customer": o["partner_id"][1] if o["partner_id"] else "unknown",
                "date": o["date_order"],
                "total": o["amount_total"],
                "status": o["state"],
            }
            for o in orders
        ]

    def search_invoices(
        self,
        customer_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        domain = [("move_type", "=", "out_invoice")]
        if customer_name:
            domain.append(("partner_id.name", "ilike", customer_name))
        if date_from:
            domain.append(("invoice_date", ">=", date_from))
        if date_to:
            domain.append(("invoice_date", "<=", date_to))

        invoices = self._execute_kw(
            "account.move", "search_read", [domain],
            {
                "fields": ["name", "partner_id", "invoice_date", "amount_total", "state", "payment_state"],
                "limit": limit,
                "order": "invoice_date desc",
            },
        )
        return [
            {
                "invoice_number": inv["name"],
                "customer": inv["partner_id"][1] if inv["partner_id"] else "Unknown",
                "date": inv["invoice_date"],
                "total": inv["amount_total"],
                "status": inv["state"],
                "payment_status": inv["payment_state"],
            }
            for inv in invoices
        ]

    def search_customers(self, name: str | None = None, limit: int = 10) -> list[dict]:
        order_partner_ids = self._execute_kw(
            "sale.order", "search_read", [[]],
            {"fields": ["partner_id"]},
        )
        partner_ids = list({o["partner_id"][0] for o in order_partner_ids if o.get("partner_id")})

        if not partner_ids:
            return []

        domain = [("id", "in", partner_ids)]
        if name:
            domain.append(("name", "ilike", name))

        partners = self._execute_kw(
            "res.partner", "search_read", [domain],
            {"fields": ["name", "email", "phone", "city", "country_id"], "limit": limit},
        )
        return [
            {
                "name": p["name"],
                "email": p.get("email") or None,
                "phone": p.get("phone") or None,
                "city": p.get("city") or None,
                "country": p["country_id"][1] if p.get("country_id") else None,
            }
            for p in partners
        ]

    def get_customer_orders_summary(self, customer_name: str) -> dict:
        domain = [("partner_id.name", "ilike", customer_name)]
        orders = self._execute_kw(
            "sale.order", "search_read", [domain],
            {"fields": ["name", "date_order", "amount_total", "state"], "order": "date_order desc"},
        )
        if not orders:
            return {"customer": customer_name, "found": False, "orders": []}

        total = sum(o["amount_total"] for o in orders)
        return {
            "customer": customer_name,
            "found": True,
            "order_count": len(orders),
            "total_spent": round(total, 2),
            "orders": [
                {
                    "order_number": o["name"],
                    "date": o["date_order"],
                    "total": o["amount_total"],
                    "status": o["state"],
                }
                for o in orders
            ],
        }

    def get_stock_levels(self, product_name: str | None = None, limit: int = 10) -> list[dict]:
        domain = []
        if product_name:
            domain.append(("product_id.name", "ilike", product_name))

        quants = self._execute_kw(
            "stock.quant", "search_read", [domain],
            {"fields": ["product_id", "location_id", "quantity"], "limit": limit},
        )
        return [
            {
                "product": q["product_id"][1] if q["product_id"] else "unknown",
                "location": q["location_id"][1] if q["location_id"] else "unknown",
                "quantity": q["quantity"],
            }
            for q in quants
        ]

    def search_product(self, name: str | None = None, limit: int = 10) -> list[dict]:
        domain = []
        if name:
            domain.append(("name", "ilike", name))

        products = self._execute_kw(
            "product.product", "search_read", [domain],
            {"fields": ["name", "list_price", "default_code"], "limit": limit},
        )
        return [
            {"name": p["name"], "price": p["list_price"], "reference": p.get("default_code") or None}
            for p in products
        ]

    def get_installed_apps(self, limit: int = 50) -> list[dict]:
        modules = self._execute_kw(
            "ir.module.module", "search_read",
            [[("state", "=", "installed"), ("application", "=", True)]],
            {"fields": ["name", "shortdesc", "summary"], "limit": limit},
        )
        return [
            {"name": m["name"], "title": m.get("shortdesc") or m["name"], "summary": m.get("summary") or None}
            for m in modules
        ]

    def get_available_apps(self, limit: int = 50) -> list[dict]:
        modules = self._execute_kw(
            "ir.module.module", "search_read",
            [[("state", "=", "uninstalled"), ("application", "=", True)]],
            {"fields": ["name", "shortdesc", "summary"], "limit": limit},
        )
        return [
            {"name": m["name"], "title": m.get("shortdesc") or m["name"], "summary": m.get("summary") or None}
            for m in modules
        ]

    def get_system_users(self, limit: int = 50) -> list[dict]:
        users = self._execute_kw(
            "res.users", "search_read",
            [[]],
            {"fields": ["name", "email", "active"], "limit": limit},
        )
        return [
            {"name": u["name"], "email": u.get("email") or None, "active": u.get("active", True)}
            for u in users
        ]

    def get_company_info(self) -> dict:
        companies = self._execute_kw(
            "res.company", "search_read", [[]],
            {"fields": ["name", "street", "city", "country_id", "phone", "email", "website"], "limit": 1, "order": "id asc"},
        )
        if not companies:
            return {"found": False}
        c = companies[0]
        return {
            "found": True,
            "name": c.get("name"),
            "address": ", ".join(filter(None, [c.get("street"), c.get("city")])) or None,
            "country": c["country_id"][1] if c.get("country_id") else None,
            "phone": c.get("phone") or None,
            "email": c.get("email") or None,
            "website": c.get("website") or None,
        }

    def get_currencies(self) -> list[dict]:
        currencies = self._execute_kw(
            "res.currency", "search_read", [[("active", "=", True)]],
            {"fields": ["name", "symbol"]},
        )
        return [{"code": c["name"], "symbol": c.get("symbol")} for c in currencies]

    def get_warehouses(self) -> list[dict]:
        warehouses = self._execute_kw(
            "stock.warehouse", "search_read", [[]],
            {"fields": ["name", "code"]},
        )
        return [{"name": w["name"], "code": w.get("code")} for w in warehouses]

    def get_sales_teams(self) -> list[dict]:
        try:
            teams = self._execute_kw(
                "crm.team", "search_read", [[]],
                {"fields": ["name", "member_ids"]},
            )
        except OdooError:
            return []
        return [{"name": t["name"], "member_count": len(t.get("member_ids") or [])} for t in teams]

    def get_product_categories(self) -> list[dict]:
        categories = self._execute_kw(
            "product.category", "search_read", [[]],
            {"fields": ["name", "complete_name"]},
        )
        return [{"name": c.get("complete_name") or c["name"]} for c in categories]

    def get_payment_methods(self) -> list[dict]:
        try:
            methods = self._execute_kw(
                "account.payment.method", "search_read", [[]],
                {"fields": ["name", "code", "payment_type"]},
            )
        except OdooError:
            return []
        return [{"name": m["name"], "type": m.get("payment_type")} for m in methods]

    def get_user_access_rights(self, name: str) -> dict:
        users = self._execute_kw(
            "res.users", "search_read",
            [["|", ("name", "ilike", name), ("login", "ilike", name)]],
            {"fields": ["name", "email", "groups_id"], "limit": 1},
        )
        if not users:
            all_users = self._execute_kw(
                "res.users", "search_read", [[]],
                {"fields": ["name"]},
            )
            all_usernames = [u["name"] for u in all_users]
            return {
                "found": False,
                "searched_name": name,
                "all_system_usernames": all_usernames,
            }

        user = users[0]
        group_ids = user.get("groups_id") or []
        groups = []
        if group_ids:
            groups = self._execute_kw(
                "res.groups", "read",
                [group_ids],
                {"fields": ["full_name", "category_id"]},
            )

        access_rights = [
            g["full_name"]
            for g in groups
            if g.get("full_name")
            and not (g.get("category_id") and g["category_id"][1].strip().lower() in _SENSITIVE_GROUP_CATEGORIES)
        ]

        return {
            "found": True,
            "name": user["name"],
            "email": user.get("email"),
            "access_rights": access_rights,
        }

    def get_area_admins(self, user_email: str) -> dict:
        users = self._execute_kw(
            "res.users", "search_read",
            [[("login", "=", user_email)]],
            {"fields": ["name", "login", "groups_id"], "limit": 1},
        )
        if not users:
            return {"found": False, "searched_email": user_email}

        current_user = users[0]
        group_ids = current_user.get("groups_id") or []
        if not group_ids:
            return {"found": True, "name": current_user["name"], "areas": []}

        my_groups = self._execute_kw(
            "res.groups", "read",
            [group_ids],
            {"fields": ["name", "full_name", "category_id"]},
        )

        my_categories = {}
        for g in my_groups:
            cat = g.get("category_id")
            if not cat:
                continue
            cat_id, cat_name = cat[0], cat[1]
            if cat_name.strip().lower() in _SENSITIVE_GROUP_CATEGORIES:
                continue
            my_categories[cat_id] = cat_name

        areas = []
        for cat_id, cat_name in my_categories.items():
            admin_groups = self._execute_kw(
                "res.groups", "search_read",
                [[("category_id", "=", cat_id), ("name", "ilike", "Administrator")]],
                {"fields": ["id", "name"]},
            )
            if not admin_groups:
                continue
            admin_group_id = admin_groups[0]["id"]
            total_admin_count = self._execute_kw(
                "res.users", "search_count",
                [[("groups_id", "in", [admin_group_id])]],
            )
            admins = self._execute_kw(
                "res.users", "search_read",
                [[("groups_id", "in", [admin_group_id])]],
                {"fields": ["name", "login"], "limit": 5},
            )
            areas.append({
                "area": cat_name,
                "admins": [{"name": a["name"], "email": a.get("login")} for a in admins],
                "total_admin_count": total_admin_count,
            })

        return {"found": True, "name": current_user["name"], "areas": areas}


# Vita Care's own Odoo, from env — used whenever no specific client is given.
_default_client = OdooClient(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD)


def _resolve(client: OdooClient | None) -> OdooClient:
    return client or _default_client


async def get_client_odoo_connection(client_key: str) -> dict | None:
    """
    Looks up one client's Odoo connection details by their client_key,
    decrypting the stored password. Not scoped to a pre-known tenant_id —
    client_key is globally unique, so this queries the pool directly
    (same pattern as /login and /tenants in main.py), rather than through
    db.tenant_connection().

    Async (unlike the rest of this module, which is XML-RPC/blocking)
    because it's a real DB round-trip via asyncpg, and every other DB
    access in this codebase already goes through the async db.pool — a
    sync call here would block the event loop instead.
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT odoo_url, odoo_db, odoo_username, odoo_password_encrypted
            FROM odoo_client_connections
            WHERE client_key = $1
            """,
            client_key,
        )
    if not row:
        return None
    return {
        "url": row["odoo_url"],
        "db": row["odoo_db"],
        "username": row["odoo_username"],
        "password": decrypt_value(row["odoo_password_encrypted"]),
    }


async def get_client_sso_secret(client_key: str) -> str | None:
    """Decrypts and returns one client's own SSO signing secret (see
    migrations/012_odoo_sso_hardening.sql) — None if the client_key is
    unknown or that client was never given a secret. Each client's Odoo
    instance holds this same value in its own Settings > General Settings >
    Vita Bot page, as the HMAC key for signing its /auth/odoo-sso requests
    (see cpbot_vita_bot_link/controllers/sso.py)."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sso_secret_encrypted FROM odoo_client_connections WHERE client_key = $1",
            client_key,
        )
    if not row or not row["sso_secret_encrypted"]:
        return None
    return decrypt_value(row["sso_secret_encrypted"])


# ---------------------------------------------------------------------------
# Backward-compatible module-level wrappers.
#
# Every function below existed before OdooClient and is called elsewhere
# (main.py's /odoo/dashboard, odoo_agent.py's tool table, build_odoo_context)
# with its original signature and zero knowledge of clients — those call
# sites keep working unchanged, always hitting Vita Care's own env-configured
# Odoo. The new optional `client` kwarg lets a caller (currently only
# odoo_agent.py, per-request) target one specific customer's Odoo instead.
# ---------------------------------------------------------------------------

def get_sales_summary(client: OdooClient | None = None) -> dict:
    return _resolve(client).get_sales_summary()


def get_top_products(limit: int = 5, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_top_products(limit)


def get_top_customers(limit: int = 5, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_top_customers(limit)


def get_customer_summary(client: OdooClient | None = None) -> dict:
    return _resolve(client).get_customer_summary()


def build_odoo_context(client: OdooClient | None = None) -> str:
    return _resolve(client).build_odoo_context()


def search_orders(
    customer_name: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
    client: OdooClient | None = None,
) -> list[dict]:
    return _resolve(client).search_orders(customer_name, status, date_from, date_to, limit)


def search_invoices(
    customer_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
    client: OdooClient | None = None,
) -> list[dict]:
    return _resolve(client).search_invoices(customer_name, date_from, date_to, limit)


def search_customers(name: str | None = None, limit: int = 10, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).search_customers(name, limit)


def get_customer_orders_summary(customer_name: str, client: OdooClient | None = None) -> dict:
    return _resolve(client).get_customer_orders_summary(customer_name)


def get_stock_levels(product_name: str | None = None, limit: int = 10, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_stock_levels(product_name, limit)


def search_product(name: str | None = None, limit: int = 10, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).search_product(name, limit)


def get_installed_apps(limit: int = 50, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_installed_apps(limit)


def get_available_apps(limit: int = 50, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_available_apps(limit)


def get_system_users(limit: int = 50, client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_system_users(limit)


def get_company_info(client: OdooClient | None = None) -> dict:
    return _resolve(client).get_company_info()


def get_currencies(client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_currencies()


def get_warehouses(client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_warehouses()


def get_sales_teams(client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_sales_teams()


def get_product_categories(client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_product_categories()


def get_payment_methods(client: OdooClient | None = None) -> list[dict]:
    return _resolve(client).get_payment_methods()


def get_user_access_rights(name: str, client: OdooClient | None = None) -> dict:
    return _resolve(client).get_user_access_rights(name)


def get_area_admins(user_email: str, client: OdooClient | None = None) -> dict:
    return _resolve(client).get_area_admins(user_email)
