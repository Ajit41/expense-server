import os
import json
import re
from flask import Flask, request, jsonify
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_prev_period(period):
    if len(period) == 6 and period.isdigit():
        year = int(period[:4])
        month = int(period[4:6])
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1
        return f"{year}{month:02d}"
    return ""

def find_txn_matches_for_period(tx_list, keyword, period):
    keyword = keyword.lower().strip()
    matches = []
    for tx in tx_list:
        if tx.get("Period") == period:
            for field in ["Transaction", "Merchant", "Title", "Category", "Method"]:
                val = tx.get(field, "")
                if keyword and keyword in str(val).lower():
                    matches.append(tx)
                    break
    return matches

def group_by_category(tx_list, period, type_value):
    summary = []
    for tx in tx_list:
        if tx.get("Period") == period and tx.get("Type") == type_value:
            cat = tx.get("Category", "Unknown")
            amt = tx.get("Amount", 0)
            found = next((item for item in summary if item["category"] == cat), None)
            if found:
                found["amount"] += amt
                found["count"] += 1
            else:
                summary.append({"category": cat, "amount": amt, "count": 1})
    return summary

def format_category_summary(summary):
    return [
        {**item, "amount": f"₹{item['amount']:.2f}"} for item in summary
    ]

def group_by_merchant(tx_list, period, merchant_category=None):
    merchants = {}
    for tx in tx_list:
        if tx.get("Period") == period:
            m = tx.get("Merchant") or tx.get("Transaction") or tx.get("Title") or "Unknown"
            amt = tx.get("Amount", 0)
            if merchant_category:
                if merchant_category.lower() not in m.lower():
                    continue
            if m in merchants:
                merchants[m]["amount"] += amt
                merchants[m]["count"] += 1
            else:
                merchants[m] = {"merchant": m, "amount": amt, "count": 1}
    return list(merchants.values())

def format_merchant_summary(summary):
    return [
        {**item, "amount": f"₹{item['amount']:.2f}"} for item in summary
    ]

def group_by_payment(tx_list, period):
    summary = {}
    for tx in tx_list:
        if tx.get("Period") == period:
            method = tx.get("Method", "Unknown")
            amt = tx.get("Amount", 0)
            summary.setdefault(method, 0)
            summary[method] += amt
    return [{"method": k, "amount": v} for k, v in summary.items()]

def format_payment_summary(summary):
    return [
        {**item, "amount": f"₹{item['amount']:.2f}" if isinstance(item['amount'], (int, float)) else str(item['amount'])}
        for item in summary
    ]

def generate_header_from_query(q, key_match=None):
    q_lower = q.lower()
    if key_match:
        if any(word in q_lower for word in ["how much", "total", "spent", "cost"]):
            return f"{key_match.strip().title()} Spend"
        if any(word in q_lower for word in ["how many", "count", "order"]):
            return f"{key_match.strip().title()} Order Count"
        if any(word in q_lower for word in ["list", "show", "all", "details"]):
            return f"{key_match.strip().title()} Details"
        return f"{key_match.strip().title()} Query"
    if "personal expense" in q_lower:
        return "Personal Expense"
    if "subscription" in q_lower:
        return "Subscription Expense"
    if "compare" in q_lower or "trend" in q_lower:
        return "Comparison / Trend"
    if "summary" in q_lower:
        return "Expense Summary"
    if "income" in q_lower:
        return "Income Overview"
    return q.strip().capitalize()[:40] or "Chat Query"

def add_smart_help_tip(chat_response, user_query):
    if not chat_response or "entries" not in chat_response:
        return chat_response
    q = user_query.lower()
    help_tip = None
    if any(kw in q for kw in ["payee", "person", "who", "to whom"]):
        help_tip = "Tip: For transaction details, tap the payee in the Reports page for a full breakdown."
    elif any(kw in q for kw in ["date wise", "by date", "datewise", "on which date", "all transactions", "each day"]):
        help_tip = "Tip: For date-wise or date-related queries, tap the category or Payment in the Reports for a full breakdown."
    elif any(kw in q for kw in ["category", "categorywise", "grouped by category"]):
        help_tip = "Tip: For category details or summary queries, tap the category in the Reports for a full breakdown."
    elif any(kw in q for kw in ["payment method", "upi", "cash", "card", "payment summary"]):
        help_tip = "Tip: For payment details or summary queries, tap Payment in the Reports for a full breakdown."
    elif any(kw in q for kw in ["month wise", "month summary", "monthly", "this month", "last month"]):
        help_tip = "Tip: For month-wise or summary queries, tap the Month in the Reports for a full breakdown."
    elif any(kw in q for kw in ["detail", "details", "summary"]):
        help_tip = "Tip: For more details, explore the Reports page for a full breakdown."
    entries = chat_response["entries"]
    detailed = any(re.match(r"\d{4}-\d{2}-\d{2}", entry.get("header", "")) for entry in entries)
    if help_tip and not detailed:
        entries.append({"header": "", "detail": help_tip})
    return chat_response

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")
    merchant_category = data.get("merchant_category")
    if not period:
        return jsonify({"error": "Missing required field: period"}), 400

    prev_period = get_prev_period(period)
    query = (data.get("query", "") or "").strip()
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)
    current_month_str = datetime.now().strftime("%Y%m")

    # Filter transactions by period and prev_period
    filtered_tx = [tx for tx in tx_list if tx.get("Period") == period]
    filtered_tx_prev = [tx for tx in tx_list if tx.get("Period") == prev_period]

    # Always build all summaries (expense=type0, income=type1)
    expense_summary = group_by_category(filtered_tx, period, 0)
    income_summary = group_by_category(filtered_tx, period, 1)
    merchant_summary = group_by_merchant(filtered_tx, period)
    payment_summary = group_by_payment(filtered_tx, period)

    expense_summary_prev = group_by_category(filtered_tx_prev, prev_period, 0)
    income_summary_prev = group_by_category(filtered_tx_prev, prev_period, 1)
    merchant_summary_prev = group_by_merchant(filtered_tx_prev, prev_period)
    payment_summary_prev = group_by_payment(filtered_tx_prev, prev_period)

    # Debugging: print your raw and total expense
    print("DEBUG | period:", period)
    print("DEBUG | expense_summary (raw):", expense_summary)
    print("DEBUG | total_expense (Type 0):", sum(item['amount'] for item in expense_summary))

    # Format only for prompt
    expense_summary_fmt = format_category_summary(expense_summary)
    expense_summary_prev_fmt = format_category_summary(expense_summary_prev)
    income_summary_fmt = format_category_summary(income_summary)
    income_summary_prev_fmt = format_category_summary(income_summary_prev)
    merchant_summary_fmt = format_merchant_summary(merchant_summary)
    merchant_summary_prev_fmt = format_merchant_summary(merchant_summary_prev)
    payment_summary_fmt = format_payment_summary(payment_summary)
    payment_summary_prev_fmt = format_payment_summary(payment_summary_prev)

    # --- PATTERN-BASED QUICK CHAT LOGIC (for microspends, quick Q&A) ---
    m_below = re.search(r"(below|under|less than|upto|micro\-spend|microspend|small)\s*₹?\s*([0-9]+)", query.lower())
    if m_below:
        amount_limit = int(m_below.group(2)) if m_below.group(2).isdigit() else 500
        matches = [tx for tx in filtered_tx if tx.get("Amount", 0) < amount_limit]
        entry_list = [{
            "header": tx.get("Title", "") or tx.get("Transaction", ""),
            "detail": f"₹{tx.get('Amount', 0):,.2f} on {tx.get('Date') or f'Period {tx.get('Period', '')}'}"
        } for tx in matches]
        resp = {
            "chat": {
                "header": f"Transactions Below ₹{amount_limit}",
                "entries": entry_list if entry_list else [{"header": "", "detail": f"No transactions below ₹{amount_limit} for {period}."}]
            }
        }
        resp["chat"] = add_smart_help_tip(resp["chat"], query)
        return jsonify(resp)

    # More chat patterns can go here (m_count, m_total, m_compare...)

    # ---- INSIGHT FLOW ----
    if not filtered_tx or (not expense_summary and not income_summary):
        return jsonify({
            "insight_groups": [{
                "header": "No Data",
                "detail": "No transactions found for the selected period.",
                "type": "empty",
                "category": "None",
                "transactions": []
            }]
        }), 200

    # --- Prompt for GPT-4o ---
prompt = f"""
You are a finance insight assistant for a personal expense tracker.

- Only use the provided summaries/data blocks for your analysis.
- Never recalculate totals or counts from raw transactions. Use ONLY the provided summaries below for your analysis.
- Always use the Indian Rupee symbol (₹) for all amounts. Do NOT use "$", "Rs", or any other currency symbol.

For every section, smart suggestion, notable trend, alert, or data point (including “small writing” and optional/creative insights):
- **You MUST always use this format for every value:**
  “₹{{amt}} at {{category}} ({{count}} entries)”  
  or  
  “₹{{amt}} in {{category}} ({{count}} entries)”
- Use “entries” (plural) unless count == 1.
- **No section, suggestion, trend, or alert is valid without this format.**

Required insight_groups (include only if relevant data is available):
- Summary (Spending Behavior)
- Income vs Expense
- Budget Alert/Remaining (if current month = period)
- Unusual/Anomaly Alerts
- Predictions/Forecasts if relevant (if current month = period)
- Saving Tip (if current month = period)
- Cash Flow
- Expense Comparison (Only if both periods have matching data)
- Spending Pattern Insights Comparison
- High Spend Category (Top 3 categories by amount)
- Biggest Single Transactions (Top 3 by amount, include details)
- Category Comparison with previous period
- Merchant-Insights (for the specified category, use merchant_summary)
- Repeated Merchant Spend
- Avoidable Spending Suggestions 
- Transaction Frequency
- Recurring Micro-Spends
- Spending Control Encouragement
- Expense Density Map
- Predictive/Recurring Bills 
- Breakdown & Awareness Insights
- Progress / Goal-Oriented Insights
- At least 4-5 Smart Suggestions (each with category, amount, and count)
- 2-3 Optional trends/alerts (including you can invent new)

**If both the current and previous period summaries have data, you MUST always include:**
- An "Expense Comparison" section comparing total expenses between the two periods.
- A "Category Comparison" section listing which categories increased, decreased, or appeared/disappeared (with amounts and counts in the format).
- A "Merchant Comparison" section comparing merchant spending between the two periods (with details if merchant data is present).
- A "Payment Comparison" section comparing Payment spending between the two periods (with details if Payment data is present).

**For Unusual/Anomaly Alerts:**
- The "Unusual/Anomaly Alerts" section must always be present in insight_groups, even if it only says "No anomalies detected".
- Always compare every category’s expense for the current and previous period, including small categories.
- If any category’s spending has increased sharply compared to the previous period (for example, by more than 50%, or any large jump in amount or number of entries), you MUST include an "Anomaly" or "Unusual Spend" alert in the insight_groups.
- Do not ignore small categories—if a category’s percentage increase is high (even if the total spend is small), you must include it as an anomaly.
- Always show both the absolute amount increase and the percentage increase for each anomaly.
- Include all categories that meet this rule, not just the largest or top ones.
- If multiple categories have sharp increases, list them all as separate alerts in the output.
- Clearly state the category name, this period’s amount and count, and the previous period’s amount and count, using the required format (“₹{{{{amt}}}} at {{{{category}}}} ({{{{count}}}} entries)”).
- Explicitly mention the percentage or amount increase and call it out as unusual or unexpected.
- Example: "Unusually high spending in Utility this month: ₹1200 (6 entries), up from ₹200 (2 entries) last month, +500%."
- If no category shows a significant increase, you MUST output an alert: "No anomalies detected" for that period.


Data available to you:
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
current_month: {current_month_str}

# EXPENSE
category_summary: {json.dumps(expense_summary_fmt, separators=(',', ':'))}
category_summary_prev: {json.dumps(expense_summary_prev_fmt, separators=(',', ':'))}

# INCOME
income_summary: {json.dumps(income_summary_fmt, separators=(',', ':'))}
income_summary_prev: {json.dumps(income_summary_prev_fmt, separators=(',', ':'))}

# MERCHANT
merchant_summary: {json.dumps(merchant_summary_fmt, separators=(',', ':'))}
merchant_summary_prev: {json.dumps(merchant_summary_prev_fmt, separators=(',', ':'))}

# PAYMENT
payment_summary: {json.dumps(payment_summary_fmt, separators=(',', ':'))}
payment_summary_prev: {json.dumps(payment_summary_prev_fmt, separators=(',', ':'))}

Respond in this JSON format:
{{
  "insight_groups": [
    {{"header": "...", "detail": "...", "type": "...", "category": "...", "transactions":[]}},
    ...
  ]
}}
"""

    try:
        chat_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a smart finance assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.65
        )
        response_text = chat_completion.choices[0].message.content
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:].strip("`").strip()
    elif response_text.startswith("```"):
        response_text = response_text[3:].strip("`").strip()

    try:
        resp_json = json.loads(response_text)
    except Exception as e:
        return jsonify({
            "parse_error": str(e),
            "raw_response": response_text
        }), 500

    def normalize_chat_entries(entries):
        normalized = []
        for entry in entries:
            if isinstance(entry, dict):
                if "amount" in entry and "category" in entry:
                    normalized.append({
                        "header": entry.get("category", ""),
                        "detail": entry.get("amount", "")
                    })
                elif "title" in entry and "value" in entry:
                    value = entry["value"]
                    if isinstance(value, list):
                        value = "\n".join(str(v) for v in value)
                    normalized.append({
                        "header": entry.get("title", ""),
                        "detail": value
                    })
                elif "content" in entry:
                    normalized.append({
                        "header": entry.get("type", ""),
                        "detail": entry.get("content", "")
                    })
                elif "detail" in entry and "header" in entry:
                    normalized.append({
                        "header": entry.get("header", ""),
                        "detail": entry.get("detail", "")
                    })
                elif "text" in entry:
                    normalized.append({
                        "header": "",
                        "detail": entry.get("text", "")
                    })
                else:
                    normalized.append({
                        "header": "",
                        "detail": ", ".join(str(v) for v in entry.values())
                    })
            else:
                normalized.append({
                    "header": "",
                    "detail": str(entry)
                })
        return normalized

    if "chat" in resp_json and "entries" in resp_json["chat"]:
        if not resp_json["chat"].get("header"):
            resp_json["chat"]["header"] = generate_header_from_query(query)
        resp_json["chat"]["entries"] = normalize_chat_entries(resp_json["chat"]["entries"])
        resp_json["chat"] = add_smart_help_tip(resp_json["chat"], query)
    return jsonify(resp_json)



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
