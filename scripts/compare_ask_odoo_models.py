"""
Side-by-side check of Ask Odoo on Claude Sonnet 5 (the live agent) vs
Gemini 2.5 Flash, before deciding whether to move Ask Odoo to Flash.

For each question it runs the real odoo_agent_ask() (Sonnet), captures the
exact system prompt that run built (live sales summary, date, identity), then
runs the same question, system prompt and TOOLS through a Gemini function-
calling loop with the same 4-round limit. Both hit the same Odoo with the same
read-only tool functions, so the only difference is the model.

Output: a Markdown report and a CSV under reports/ with each answer, the
tools each model called, rounds, latency, tokens and estimated cost. Grading
is by a person reading the two answers side by side — check the numbers
against Odoo, especially totals and "my permissions" answers.

Costs real API money (both models) and reads the real Odoo — run it with
the same env as the backend (ANTHROPIC_API_KEY, GEMINI_API_KEY, ODOO_*).
Uses Vita Care's default env Odoo; client-company connections aren't wired
in here.

Usage:
    python scripts/compare_ask_odoo_models.py
    python scripts/compare_ask_odoo_models.py --questions my_questions.txt
    python scripts/compare_ask_odoo_models.py --email manager@vitacare.sa
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from functools import partial

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv

# Before core.ai_client is imported: it reads the API keys at import time.
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from google.genai import types

from core.ai_client import gemini_client, GEMINI_FLASH_MODEL, SONNET_MODEL
from services import odoo_agent, odoo_service

# Estimated list prices, USD per million tokens. Sonnet cache writes are
# 1.25x input, cache reads 0.1x. Flash thinking tokens bill as output.
SONNET_PRICE = {"in": 2.00, "out": 10.00, "cache_write": 2.50, "cache_read": 0.20}
FLASH_PRICE = {"in": 0.30, "out": 2.50}

DEFAULT_QUESTIONS = [
    "What is our total revenue this month?",
    "كم عدد الطلبات اليوم؟",
    "Who are the top 5 customers this year?",
    "أفضل 10 منتجات مبيعاً هذا الشهر",
    "Show me a chart of the top products by revenue this month",
    "Which products are low in stock?",
    "كم المخزون المتوفر من بنادول؟",
    "List the unpaid invoices from last week",
    "What are my permissions?",
    "What access rights does the support team have?",
    "Which warehouses do we have?",
    "Compare sales this month with last month",
    "مين أكثر عميل اشترى من أول السنة؟",
    "How do I create a new sales order?",
]

FLASH_THINKING_BUDGET = 1024


def _noop(*args, **kwargs):
    pass


# Keep test runs out of the AI monitoring table.
odoo_agent.log_ai_prediction = _noop


class SonnetRecorder:
    """Wraps anthropic_client.messages.create to record usage and the
    system prompt of each call, without changing what the agent does."""

    def __init__(self, client):
        self._create = client.messages.create
        client.messages.create = self._wrapped
        self.reset()

    def reset(self):
        self.calls = []
        self.system = None

    def _wrapped(self, **kwargs):
        if self.system is None:
            self.system = kwargs.get("system")
        response = self._create(**kwargs)
        self.calls.append(response)
        return response

    def summary(self):
        u = {"in": 0, "out": 0, "cache_write": 0, "cache_read": 0}
        tools = []
        for r in self.calls:
            u["in"] += r.usage.input_tokens or 0
            u["out"] += r.usage.output_tokens or 0
            u["cache_write"] += r.usage.cache_creation_input_tokens or 0
            u["cache_read"] += r.usage.cache_read_input_tokens or 0
            tools += [b.name for b in r.content if b.type == "tool_use"]
        cost = sum(u[k] * SONNET_PRICE[k] for k in u) / 1_000_000
        return u, tools, cost


def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "".join(block["text"] for block in system)


def run_sonnet(recorder, question, email):
    recorder.reset()
    start = time.time()
    error = None
    try:
        result = odoo_agent.odoo_agent_ask(question, current_user_email=email)
    except Exception as e:
        result, error = {"answer": "", "chart": None}, f"{type(e).__name__}: {e}"
    latency = time.time() - start
    usage, tools, cost = recorder.summary()
    return {
        "answer": result["answer"],
        "chart": bool(result["chart"]),
        "tools": tools,
        "rounds": len(recorder.calls),
        "latency_s": round(latency, 1),
        "tokens": usage,
        "cost": cost,
        "error": error,
    }, recorder.system


def _gemini_tools():
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters_json_schema=t["input_schema"],
        )
        for t in odoo_agent.TOOLS
    ])]


def run_flash(question, system_text, max_tool_rounds=4):
    """The same loop as odoo_agent_ask, in Gemini function-calling form."""
    tool_functions = {name: partial(fn, client=None) for name, fn in odoo_agent._TOOL_FUNCTIONS.items()}
    config = types.GenerateContentConfig(
        system_instruction=system_text,
        tools=_gemini_tools(),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types.ThinkingConfig(thinking_budget=FLASH_THINKING_BUDGET),
        max_output_tokens=2500 + FLASH_THINKING_BUDGET,
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
    usage = {"in": 0, "out": 0, "thinking": 0}
    tools, chart, answer, error, rounds = [], False, "", None, 0
    start = time.time()
    try:
        for _ in range(max_tool_rounds):
            rounds += 1
            response = gemini_client.models.generate_content(
                model=GEMINI_FLASH_MODEL, contents=contents, config=config,
            )
            meta = response.usage_metadata
            usage["in"] += meta.prompt_token_count or 0
            usage["out"] += meta.candidates_token_count or 0
            usage["thinking"] += meta.thoughts_token_count or 0

            # Append the model's own content (keeps its thought signatures).
            contents.append(response.candidates[0].content)
            calls = response.function_calls or []
            if not calls:
                answer = response.text or ""
                break

            parts = []
            for call in calls:
                tools.append(call.name)
                args = dict(call.args or {})
                if call.name == "present_chart":
                    chart = True
                    result = {"status": "chart displayed to user"}
                else:
                    func = tool_functions.get(call.name)
                    if func is None:
                        result = {"error": f"Unknown tool:{call.name}"}
                    else:
                        try:
                            result = func(**args)
                        except odoo_service.OdooError as e:
                            result = {"error": str(e)}
                        except Exception as e:
                            result = {"error": f"{type(e).__name__}: {e}"}
                parts.append(types.Part.from_function_response(
                    name=call.name,
                    response={"result": json.loads(json.dumps(result, default=str))},
                ))
            contents.append(types.Content(role="user", parts=parts))
        else:
            answer = "(hit the 4-round limit without answering)"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    latency = time.time() - start
    cost = (usage["in"] * FLASH_PRICE["in"] + (usage["out"] + usage["thinking"]) * FLASH_PRICE["out"]) / 1_000_000
    return {
        "answer": answer,
        "chart": chart,
        "tools": tools,
        "rounds": rounds,
        "latency_s": round(latency, 1),
        "tokens": usage,
        "cost": cost,
        "error": error,
    }


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", help="Text file, one question per line (default: built-in list)")
    parser.add_argument("--email", help="Signed-in user's email, for 'my permissions' questions")
    parser.add_argument("--out", default="reports", help="Output folder (default: reports)")
    args = parser.parse_args()

    if args.questions:
        with open(args.questions, encoding="utf-8") as f:
            questions = [line.strip() for line in f if line.strip()]
    else:
        questions = DEFAULT_QUESTIONS

    recorder = SonnetRecorder(odoo_agent.anthropic_client)
    rows = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q}")
        sonnet, system = run_sonnet(recorder, q, args.email)
        if system is None:
            flash = {"answer": "", "chart": False, "tools": [], "rounds": 0, "latency_s": 0,
                     "tokens": {}, "cost": 0, "error": "skipped: Sonnet run failed before its first call"}
        else:
            flash = run_flash(q, _system_text(system))
        print(f"    sonnet ${sonnet['cost']:.4f} {sonnet['latency_s']}s {sonnet['tools']}")
        print(f"    flash  ${flash['cost']:.4f} {flash['latency_s']}s {flash['tools']}")
        rows.append({"question": q, "sonnet": sonnet, "flash": flash})

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    csv_path = os.path.join(args.out, f"ask_odoo_compare_{stamp}.csv")
    md_path = os.path.join(args.out, f"ask_odoo_compare_{stamp}.md")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["question", "model", "answer", "chart", "tools", "rounds", "latency_s", "tokens", "cost_usd", "error"])
        for r in rows:
            for model in ("sonnet", "flash"):
                m = r[model]
                w.writerow([r["question"], model, m["answer"], m["chart"], " > ".join(m["tools"]),
                            m["rounds"], m["latency_s"], json.dumps(m["tokens"]), f"{m['cost']:.5f}", m["error"] or ""])

    n = len(rows)
    totals = {
        model: {
            "cost": sum(r[model]["cost"] for r in rows),
            "latency": sum(r[model]["latency_s"] for r in rows) / n,
            "errors": sum(1 for r in rows if r[model]["error"]),
            "charts": sum(1 for r in rows if r[model]["chart"]),
        }
        for model in ("sonnet", "flash")
    }
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Ask Odoo: {SONNET_MODEL} vs {GEMINI_FLASH_MODEL}\n\n")
        f.write(f"{n} questions, run {datetime.now():%Y-%m-%d %H:%M}. Costs are estimates from token counts.\n\n")
        f.write("| | Sonnet | Flash |\n|---|---|---|\n")
        f.write(f"| Avg cost / question | ${totals['sonnet']['cost'] / n:.4f} | ${totals['flash']['cost'] / n:.4f} |\n")
        f.write(f"| Per 1,000 questions | ${totals['sonnet']['cost'] / n * 1000:.0f} | ${totals['flash']['cost'] / n * 1000:.0f} |\n")
        f.write(f"| Avg latency | {totals['sonnet']['latency']:.1f}s | {totals['flash']['latency']:.1f}s |\n")
        f.write(f"| Errors | {totals['sonnet']['errors']} | {totals['flash']['errors']} |\n")
        f.write(f"| Charts shown | {totals['sonnet']['charts']} | {totals['flash']['charts']} |\n\n")
        f.write("Mark each question: Same / Sonnet better / Flash better / Both wrong. Check numbers against Odoo.\n\n")
        for i, r in enumerate(rows, 1):
            s, fl = r["sonnet"], r["flash"]
            f.write(f"## {i}. {r['question']}\n\n")
            f.write("| | Sonnet | Flash |\n|---|---|---|\n")
            f.write(f"| Answer | {_cell(s['error'] or s['answer'])} | {_cell(fl['error'] or fl['answer'])} |\n")
            f.write(f"| Tools | {' > '.join(s['tools']) or '-'} | {' > '.join(fl['tools']) or '-'} |\n")
            f.write(f"| Chart | {'yes' if s['chart'] else 'no'} | {'yes' if fl['chart'] else 'no'} |\n")
            f.write(f"| Rounds / time | {s['rounds']} / {s['latency_s']}s | {fl['rounds']} / {fl['latency_s']}s |\n")
            f.write(f"| Cost | ${s['cost']:.4f} | ${fl['cost']:.4f} |\n\n")
            f.write("Verdict: \n\n")

    print(f"\nReport: {md_path}\nCSV:    {csv_path}")


if __name__ == "__main__":
    main()
