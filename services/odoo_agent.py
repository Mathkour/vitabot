import json
import time
from functools import partial

from core.ai_client import anthropic_client, SONNET_MODEL
from services import odoo_service
from services.ai_monitoring import log_ai_prediction
from services.odoo_service import OdooClient


system_prompt = """You are an assistant that answers questions about a company's Odoo data
(sales orders, invoices, customers, products, stock levels).

CRITICAL FORMATTING RULE: Never use Markdown syntax in your response — no asterisks for
bold/italic (**text** or *text*), no pound signs for headers (# Header), no markdown bullet
points (- item or * item). Write in plain, natural text only. If you need to list items, use
plain numbered lines (1. 2. 3.) followed by a period and space, or simple line breaks — never
markdown formatting symbols.

CRITICAL RULE: For ANY question that mentions a specific customer, product, order, or invoice
by name — or asks about totals, counts, or history — you MUST call the appropriate tool FIRST
before answering. Never answer from memory or assumption. If you are even slightly unsure
whether a tool applies, call it anyway and check the result.

CONTEXT RULE: This conversation may include previous messages. If the user refers to "him",
"her", "them", "that customer", "it", or otherwise omits a name that was already mentioned
earlier in the conversation, resolve the reference from the conversation history yourself —
do NOT ask the user to repeat a name they already gave. Only ask for clarification if the
name genuinely was never mentioned anywhere in the conversation.

SCOPE RULE FOR HOW-TO / USAGE QUESTIONS: This assistant's main purpose is answering questions
about the company's actual Odoo DATA via the provided tools (sales, customers, inventory,
permissions, system info, etc.). For "how do I..." / "how can I..." procedural or usage
questions, check the RELEVANT COMPANY MANUAL EXCERPTS provided below in this system message
(if any) — if they actually answer the question, use them to give an accurate, specific answer based on that
real content, optionally mentioning any attached video/media referenced in it. Do NOT invent
or supplement steps from your own general knowledge of Odoo, even if the excerpts are
incomplete — only state what the excerpts actually say. If the excerpts don't cover the
question at all, clearly say this isn't something you have specific guidance for here, and
suggest asking in the main chat assistant instead of guessing.

CRITICAL COMPLETENESS RULE: When answering from the RELEVANT COMPANY MANUAL EXCERPTS, you MUST
include EVERY step, field name, option, and note/warning mentioned in the excerpt — do not
summarize, shorten, or skip any part of it, even if it seems minor. If the excerpt describes
more than one method or scenario, present all of them, not just the first one.

TOOL SELECTION RULES (follow these exactly — picking the wrong tool gives WRONG numbers):

- Questions about OVERALL totals ("how many orders total", "total revenue", "who is our
  overall top customer by spend") → use get_sales_summary ONLY, or read the VERIFIED SALES
  SUMMARY already provided below in this system message. Never try to compute totals
  yourself from a list of orders or invoices.

- Questions about ONE specific customer's history ("what did X buy", "how much has X spent
  in total", "how many orders has X made", "what was their last order/purchase") → use
  get_customer_orders_summary ONLY. This aggregates ALL of that customer's orders correctly
  and is sorted by date descending, so the first order in the list is the most recent one.

- search_orders and search_invoices return RAW LISTS of individual records (capped by
  `limit`, default 10). They are for browsing/listing specific records (e.g. "show me
  Gemini Furniture's last 5 orders", "list open invoices for Azure Interior"). NEVER use
  them to answer aggregate/total/"who is the biggest" questions — a single invoice or a
  partial list is not a total, and picking one row and calling it "the total" or "the
  biggest" is a WRONG answer even if a number is returned.

- search_customers is for looking up contact info (email, phone, city) by name — not for
  spend or order data.

- Questions about "top N customers" or "best customers by purchase amount" (e.g. "top 5
  customers", "who are our best 10 customers") → use get_top_customers ONLY. It returns
  customers already sorted descending by total spend, computed and sorted by the code itself
  — never rank or sort customers yourself from search_orders, search_invoices, or any other
  tool's results; that ordering is not reliable and has produced wrong rankings before. Pass
  the number the user asked for as `limit` (default 5 if unspecified); for "the top customer"
  singular with no number, use limit=1.

- Questions about "best-selling product(s)" or "top products" ("what's our top product",
  "what sells the most") → use get_top_products ONLY. Never infer a product name from an
  order number, invoice number, or any other unrelated tool result — always call
  get_top_products directly to get the actual product name.

- get_stock_levels and search_products are for inventory/catalog questions only.

- Questions about installed apps/modules → get_installed_apps. Questions about apps available
  to install → get_available_apps. Questions about system users → get_system_users (returns
  basic contact info only — name, email, active status. Never discuss permissions, security
  groups, or settings via this tool; use get_user_access_rights instead for those, per the
  rule below).

- Questions about a specific user's permissions/access rights ("what are X's access rights",
  "what permissions does X have") → get_user_access_rights ONLY. This tool is strictly
  read-only and returns only functional/business access groups (e.g. Sales, Inventory,
  Invoicing, User type) — it deliberately excludes Administration, Settings, and
  technical-level permissions, which are never available through this assistant under any
  tool. Never suggest or imply that permissions can be changed through this assistant, and
  never attempt to call any modification. If the user isn't found, follow the USER NAME
  MATCHING RULE below rather than guessing. If asked specifically about
  Settings/Administration/technical permissions or API keys, politely say that information
  isn't available through this assistant.

- If the user asks about "my" permissions/access rights, or asks you to identify them
  ("who am I", "do you know me", "introduce yourself to me"), and a CURRENT USER IDENTITY
  is provided in this system message, use that identity's email with get_user_access_rights
  automatically — do not ask them to repeat their name or email.

- "Who is my admin / who manages my area" → use get_area_admins with the current user's email
  (from CURRENT USER IDENTITY above if available, or ask for their email if not). This only
  returns functional-area administrators (like Inventory Administrator), never system
  Settings-level access. Each area's admin list is capped at 5 names with a total_admin_count —
  mention a couple of names plus the total (e.g. "X, Y and 6 others (8 total)") rather than
  reading out a long list.

- If asked "can I do X" (e.g. "can I add a tax", "can I delete an invoice", "am I allowed to
  edit products"), call get_user_access_rights for the relevant user (use CURRENT USER IDENTITY
  if the question is about "I/me"), then INTERPRET the returned access_rights list yourself to
  give a direct answer — do not refuse or say you don't know. Reason about which returned group
  names plausibly cover the requested action (e.g. "Accounting / Billing" or "Invoicing /
  Administrator" implies invoice-related actions; "Sales / User: All Documents" implies broad
  sales access). If you're not fully certain a specific action is covered, say what access they
  DO have and note that exact permission granularity isn't always visible from group names alone
  — but always give a substantive, helpful answer rather than a flat refusal or apology.

USER NAME MATCHING RULE: If get_user_access_rights returns found=false, it will include
all_system_usernames (the full real list of usernames in the system). The searched name may
have been given in a different language or script than how it's stored (e.g. an Arabic
phonetic spelling of an English name like "سبورت تيم" for "support team", or vice versa) —
use your own knowledge of cross-language phonetic correspondence to find the most likely
actual match in all_system_usernames yourself. If you find one clear likely match, call
get_user_access_rights again with that exact name from the list, then present the result
while noting which name you matched it to (e.g. "I found this under 'support team':"). If
there are multiple plausible matches or you're not confident, ask the user to confirm which
one they meant by listing the top candidates. If nothing in the list is remotely plausible,
say clearly no matching user was found.

CHART RULE: Whenever ANY tool call returns more than one item with a comparable numeric value
attached (regardless of which tool — sales totals, product quantities, stock levels, revenue,
counts, etc.), you MUST also call present_chart using that data (labels = item names, values =
their numeric values) before giving your final answer. This applies generally, not just to
specific named tools. A short text summary should still accompany the chart. Only skip
present_chart for genuinely single-value or single-item answers (one specific total, one
customer's info, a yes/no question).

GENERAL RULES:
- ONLY use the provided tools (or the verified summary below) to look up real data. Never
  invent numbers, dates, names, or IDs.
- If a tool returns no results (found: false, or an empty list), say clearly that you don't
  have that information — do not guess or make up an answer.
- If the user's question is genuinely ambiguous (no name anywhere in history), ask a short
  clarifying question instead of guessing.
- Answer in the same language the user asked in (Arabic or English).
- Keep answers concise and directly useful — include concrete numbers/names from the tool
  results, not vague summaries.
- If you're unsure whether you picked the right tool for a totals-style question, re-check:
  did the tool return a pre-aggregated total, or just one row from a list? If it's just one
  row, that is NOT the answer to a "total" or "biggest" question — call the correct
  aggregate tool instead.
"""

TOOLS = [
    {
        "name": "search_orders",
        "description": "Search a LIST of individual sales orders (raw records, not aggregated). "
                       "Use for browsing/listing specific orders only. Do NOT use for 'total spent' "
                       "or 'top customer' questions — use get_sales_summary or "
                       "get_customer_orders_summary instead for those.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Partial or full customer name"},
                "status": {"type": "string", "enum": ["draft", "sent", "sale", "done", "cancel"]},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
            },
        },
    },
    {
        "name": "search_invoices",
        "description": "Search a LIST of individual customer invoices (raw records, not aggregated). "
                       "Use for browsing/listing specific invoices only. Do NOT use for 'total spent' "
                       "or 'top customer' questions — use get_sales_summary or "
                       "get_customer_orders_summary instead for those.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
            },
        },
    },
    {
        "name": "search_customers",
        "description": "Search customers by name, returns contact info (email, phone, city). "
                       "Not for spend or order history questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
            },
        },
    },
    {
        "name": "get_customer_orders_summary",
        "description": "Get ALL orders and total amount spent for one specific customer by name, "
                       "sorted by date descending (most recent first). Use this for 'what did X buy', "
                       "'how much has X spent', 'what was X's last order' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
            },
            "required": ["customer_name"],
        },
    },
    {
        "name": "get_top_products",
        "description": "Get the top-selling products ranked by revenue, with quantity sold and "
                       "total revenue for each. Use this for 'what is our best-selling product' "
                       "or 'top products' questions. Returns clean product names only — never "
                       "infer a product name from an order number or any other unrelated result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many top products to return, default 5"},
            },
        },
    },
    {
        "name": "get_top_customers",
        "description": "Get the top N customers ranked by total amount spent, in guaranteed "
                       "descending order (highest spender first). ALWAYS use this for any "
                       "'top N customers' or 'best customers by purchase amount' question — "
                       "never try to rank customers yourself from other tool results, the "
                       "ordering from those is not reliable. The limit parameter accepts any "
                       "number the user asks for (3, 10, 15, 50, etc.) — default is 5 only if "
                       "the user doesn't specify a number. If the user asks for just 'the top "
                       "customer' (singular, no number), call with limit=1.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many top customers to return, default 5"},
            },
        },
    },
    {
        "name": "get_stock_levels",
        "description": "Get current stock/inventory quantities, optionally filtered by product name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
            },
        },
    },
    {
        "name": "search_products",
        "description": "Search products by name, returns price and reference code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
            },
        },
    },
    {
        "name": "get_installed_apps",
        "description": "Get the list of currently installed Odoo apps/modules with their names and "
                       "descriptions. Use for 'what apps do I have installed' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results, default 50"},
            },
        },
    },
    {
        "name": "get_available_apps",
        "description": "Get the list of Odoo apps/modules that are available but NOT yet installed. "
                       "Use for 'what apps can I install' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results, default 50"},
            },
        },
    },
    {
        "name": "get_system_users",
        "description": "Get the basic list of Odoo system users (name, email, active status only — "
                       "no permissions or security details). Use for 'who are our system users' "
                       "questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results, default 50"},
            },
        },
    },
    {
        "name": "get_company_info",
        "description": "Get basic company information: name, address, phone, email, website. "
                       "Use for 'what's our company name/address' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_currencies",
        "description": "Get the list of active currencies configured in the system. Use for "
                       "'what currencies do we use' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_warehouses",
        "description": "Get the list of warehouses/branches. Use for 'how many warehouses/branches "
                       "do we have' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_sales_teams",
        "description": "Get the list of sales teams and their member counts. Use for 'what sales "
                       "teams do we have' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_product_categories",
        "description": "Get the list of product categories. Use for 'what product categories do "
                       "we have' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_payment_methods",
        "description": "Get the list of available payment methods. Use for 'what payment methods "
                       "do we support' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_user_access_rights",
        "description": "Get the Odoo access rights / permission groups assigned to a specific system "
                       "user by name (read-only — this only reports what access a user currently has, "
                       "it never changes anything). Returns only functional/business groups (Sales, "
                       "Inventory, Invoicing, User type, etc.) — Administration, Settings, and "
                       "technical-level groups are deliberately excluded and never returned. Use for "
                       "'what are X's permissions/access rights' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full or partial name of the user"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_area_admins",
        "description": "Find who has Administrator-level access in the same functional areas "
                       "(e.g. Inventory, Sales, Accounting — never system Settings/Administration) "
                       "as a given user. Use for 'who is my admin' or 'who manages the Inventory "
                       "area' style questions. Requires the user's email. Each area's 'admins' list "
                       "is capped at 5 names for readability — 'total_admin_count' has the real total, "
                       "so if it's higher than the number of names shown, say something like 'X and 4 "
                       "others (N total)' rather than implying those are the only admins.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_email": {"type": "string", "description": "Email of the user whose functional area admins to look up"},
            },
            "required": ["user_email"],
        },
    },
    {
        "name": "present_chart",
        "description": "Call this when the answer involves comparing multiple items (e.g. several "
                       "customers, products, or categories with comparable numeric values) and would "
                       "be clearer as a chart than as a text list. Do NOT call this for single-value "
                       "answers (e.g. 'who was the last customer', 'how much did X spend total') — "
                       "those should remain plain text only. Choose chart_type based on what fits best: "
                       "'bar' for comparing values across several items (revenue by customer, quantity "
                       "by product), 'pie' for showing proportional share of a whole (e.g. distribution "
                       "of orders by status). Provide clean, human-readable labels (no IDs or codes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "pie"]},
                "title": {"type": "string", "description": "Short chart title, in the same language as the user's question"},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Category labels, e.g. customer or product names"},
                "values": {"type": "array", "items": {"type": "number"}, "description": "Numeric values matching each label, same order and length as labels"},
            },
            "required": ["chart_type", "title", "labels", "values"],
        },
    },
]

_TOOL_FUNCTIONS = {
    "search_orders": odoo_service.search_orders,
    "search_invoices": odoo_service.search_invoices,
    "search_customers": odoo_service.search_customers,
    "get_customer_orders_summary": odoo_service.get_customer_orders_summary,
    "get_top_products": odoo_service.get_top_products,
    "get_top_customers": odoo_service.get_top_customers,
    "get_stock_levels": odoo_service.get_stock_levels,
    "search_products": odoo_service.search_product,
    "get_installed_apps": odoo_service.get_installed_apps,
    "get_available_apps": odoo_service.get_available_apps,
    "get_system_users": odoo_service.get_system_users,
    "get_company_info": odoo_service.get_company_info,
    "get_currencies": odoo_service.get_currencies,
    "get_warehouses": odoo_service.get_warehouses,
    "get_sales_teams": odoo_service.get_sales_teams,
    "get_product_categories": odoo_service.get_product_categories,
    "get_payment_methods": odoo_service.get_payment_methods,
    "get_user_access_rights": odoo_service.get_user_access_rights,
    "get_area_admins": odoo_service.get_area_admins,
}


def odoo_agent_ask(
    question: str,
    history: list[dict] | None = None,
    current_user_email: str | None = None,
    current_username: str | None = None,
    kb_context: list[str] | None = None,
    client_connection: dict | None = None,
    max_tool_rounds: int = 4,
    tenant_id: str | None = None,
) -> dict:
    """
    question: السؤال الحالي من المستخدم
    history: قائمة رسايل سابقة بنفس المحادثة، بصيغة [{"role": "user"/"assistant", "content": "..."}]
             (نفس شكل history تبع endpoint /ask الرئيسي) - اختياري، افتراضياً None
    current_user_email / current_username: هوية المستخدم المسجل دخوله بحساب cpbot الحالي،
             تُستخدم تلقائياً لأسئلة مثل "شو صلاحياتي" بدون ما يذكر اسمه/إيميله - اختياري
    kb_context: مقاطع من الـ Knowledge Base (نفس مصدر /ask الرئيسي) ذات صلة محتملة بالسؤال،
             تُستخدم لأسئلة "كيف أعمل X" بدل الرفض أو التخمين - اختياري
    client_connection: بيانات اتصال أودو عميل معيّن (dict من odoo_service.get_client_odoo_connection)،
             إذا None بيستخدم أودو Vita Care الافتراضي من env - اختياري

    يرجّع dict: {"answer": str, "chart": dict | None}. chart موجود فقط إذا استدعى
    الموديل present_chart بهذه الجلسة (وبآخر شكل استدعاها فيه لو تكرر الاستدعاء).
    """
    # None here (not client_connection) means "use Vita Care's default env
    # Odoo" everywhere downstream — every tool function's `client` kwarg
    # (odoo_service.py's own parameter name, unrelated to this variable)
    # already treats None that way, so there's nothing else to branch on.
    odoo_client = OdooClient(**client_connection) if client_connection else None

    chart_payload: dict | None = None
    try:
        verified_summary = odoo_service.get_sales_summary(client=odoo_client)
        summary_context = (
            "\n\nVERIFIED CURRENT SALES SUMMARY (already computed, use this directly for "
            "any question about total orders, total revenue, or overall top customer — "
            "do NOT call a tool to recompute these, just read the numbers below):\n"
            + json.dumps(verified_summary, ensure_ascii=False)
        )
    except odoo_service.OdooError:
        summary_context = ""

    identity_context = ""
    if current_user_email:
        identity_context = (
            f"\n\nCURRENT USER IDENTITY: The person you are talking to is logged into the "
            f"company chatbot with the email '{current_user_email}'"
            + (f" and display name '{current_username}'" if current_username else "")
            + ". When they ask about 'my permissions', 'my access rights', ask you to identify "
            "them ('who am I', 'do you know me'), or otherwise refer to themselves without "
            f"naming someone else, you MUST call get_user_access_rights with name="
            f"'{current_user_email}' — pass the exact email string above, NOT the display name, "
            "even if a display name was also given, since the display name may not match Odoo's "
            "record. If no matching Odoo user is found for this email, clearly tell them no Odoo "
            "user is registered with this email — do not guess or assume they are a different user, "
            "and do not retry the lookup with the display name instead.\n\n"
            "IMPORTANT PRECEDENCE RULE: If the question names or references a specific person or user "
            "(by name, username, role like \"support team\", or any other explicit identifier) as the "
            "subject of the question — even indirectly, e.g. \"can X do Y from their end\" — always resolve "
            "that NAMED entity with get_user_access_rights, using their name. Do NOT substitute the current "
            "user's own identity/email in this case. Only use the CURRENT USER IDENTITY (current user's own "
            "email) when the question is unambiguously about the speaker themselves — phrases like \"my "
            "permissions\", \"can I do X\", \"who am I\" with no other person mentioned. When in doubt about "
            "whether a pronoun refers to the current user or a named entity mentioned earlier in the same "
            "question, prefer the named entity."
        )

    kb_context_text = ""
    if kb_context:
        kb_context_text = (
            "\n\nRELEVANT COMPANY MANUAL EXCERPTS (may or may not be relevant to this specific "
            "question — use them only if they actually answer it):\n"
            + "\n---\n".join(kb_context)
        )

    full_system_prompt = system_prompt + summary_context + identity_context + kb_context_text

    messages = []
    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    # Bound to this one request's Odoo client (or None = default) — never
    # shared across requests, so two concurrent questions for two different
    # client companies can never cross-call each other's Odoo.
    tool_functions = {name: partial(fn, client=odoo_client) for name, fn in _TOOL_FUNCTIONS.items()}

    for _ in range(max_tool_rounds):
        start_time = time.time()
        try:
            response = anthropic_client.messages.create(
                model=SONNET_MODEL,
                max_tokens=2500,
                system=full_system_prompt,
                tools=TOOLS,
                messages=messages,
            )
            log_ai_prediction(
                tenant_id=tenant_id, endpoint="odoo_agent", model_used=SONNET_MODEL,
                request_summary=question, response_time_ms=round((time.time() - start_time) * 1000),
                status="success",
            )
        except Exception as e:
            log_ai_prediction(
                tenant_id=tenant_id, endpoint="odoo_agent", model_used=SONNET_MODEL,
                request_summary=question, response_time_ms=round((time.time() - start_time) * 1000),
                status="timeout" if "timeout" in type(e).__name__.lower() else "error",
                error_message=str(e),
            )
            raise

        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            answer = next((b.text for b in response.content if b.type == "text"), None) or "عذراً، ما قدرت أطلع جواب."
            return {"answer": answer, "chart": chart_payload}

        tool_results = []
        for tool_call in tool_use_blocks:
            func_name = tool_call.name
            args = tool_call.input or {}

            if func_name == "present_chart":
                chart_payload = args
                result = {"status": "chart displayed to user"}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result, default=str, ensure_ascii=False),
                })
                continue

            func = tool_functions.get(func_name)
            if func is None:
                result = {"error": f"Unknown tool:{func_name}"}
            else:
                try:
                    result = func(**args)
                except odoo_service.OdooError as e:
                    result = {"error": str(e)}
                except Exception as e:
                    result = {"error": f"Tool execution failed:{e}"}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "في تعقيد بالسؤال أكتر من اللازم، ممكن تعيد صياغته بشكل أبسط؟",
        "chart": chart_payload,
    }