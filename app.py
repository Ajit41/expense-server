import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from openai import OpenAI
from collections import defaultdict

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_prev_period(period_str):
    try:
        dt = datetime.strptime(period_str, "%Y%m")
        year, month = dt.year, dt.month - 1
        if month == 0:
            year -= 1
            month = 12
        return f"{year:04d}{month:02d}"
    except Exception:
        return ""

def group_by_category(transactions, period, type_val):
    summary = defaultdict(lambda: {'Amount': 0, 'Count': 0})
    for tx in transactions:
        if tx.get("Period") == period and tx.get("Type") == type_val:
            cat = tx.get("Category", "Unknown")
            summary[cat]['Amount'] += float(tx.get("Amount", 0))
            summary[cat]['Count'] += 1
    return [
        {"Category": cat, "Amount": round(v['Amount'], 2), "Count": v['Count']}
        for cat, v in summary.items()
    ]

def group_by_merchant(transactions, period, category):
    summary = defaultdict(lambda: {'Amount': 0, 'Count': 0})
    for tx in transactions:
        if tx.get("Period") == period and tx.get("Category") == category:
            merchant = tx.get("Transaction", "Unknown")
            summary[merchant]['Amount'] += float(tx.get("Amount", 0))
            summary[merchant]['Count'] += 1
    return [
        {"Merchant": m, "Amount": round(v['Amount'], 2), "Count": v['Count']}
        for m, v in summary.items()
    ]

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data        = request.get_json()
    tx_list     = data.get("transactions", [])
    period      = data.get("period", "")
    merchant_category = data.get("merchant_category")  # now user can pass any category name
    if not period:
        return jsonify({"error": "Missing required field: period"}), 400

    prev_period = get_prev_period(period)
    query       = data.get("query", "")
    budget      = data.get("budget", 0)
    days_left   = data.get("days_left", 0)

    allowed_periods = {period, prev_period}
    filtered_tx = [tx for tx in tx_list if tx.get("Period") in allowed_periods]
    filtered_tx = filtered_tx[:1000]  # Token safety cap

    if not filtered_tx:
        return jsonify({
            "insight_groups": [{
                "header": "No Data",
                "detail": "No transactions found for the selected period.",
                "type": "empty",
                "category": "None",
                "transactions": []
            }]
        }), 200

    # Summaries for current period only
    expense_summary = group_by_category(filtered_tx, period, 0)
    income_summary  = group_by_category(filtered_tx, period, 1)
    merchant_summary = []
    if merchant_category:
        merchant_summary = group_by_merchant(filtered_tx, period, merchant_category)

    # Compose prompt for GPT
    if not query:
        prompt = f"""
You are a finance insight assistant for a personal expense tracker.

- Use ONLY the provided summaries below for all your category-level analysis.
- Do NOT analyze individual transactions for category totals—use the pre-calculated summaries.
- For Merchant-Insights, use the merchant_summary for the requested category if available.
- For any other merchant-level insights, ask for a summary.

category_summary: {json.dumps(expense_summary, separators=(',', ':'))}
income_summary: {json.dumps(income_summary, separators=(',', ':'))}
merchant_summary: {json.dumps(merchant_summary, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}

Required insight_groups:
- Summary (Spending Behavior)
- Income vs Expense
- High Spend (Top 3 categories by amount)
- Expense Comparison (Only if both periods have matching data)
- Remaining Budget (if budget > 0)
- Payment Method
- Recurring Bill
- Forecast
- Saving Tip
- Savings Trend
- Cash Flow
- Longest Expense Streak
- Merchant-Insights (for the specified category, use merchant_summary)
- At least 2 Smart Suggestions (each with category, amount, and count)
- Other Notable Trends (optional)

Respond in this JSON format:
{{
  "insight_groups": [
    {{"header": "...", "detail": "...", "type": "...", "category": "...", "transactions":[]}},
    ...
  ]
}}
"""
    else:
        prompt = f"""
You are a smart financial chat assistant.
Use ONLY the provided category/income/merchant summaries for your analysis.
Never guess or make assumptions. If no matching data exists: return “No data for this period.”

category_summary: {json.dumps(expense_summary, separators=(',', ':'))}
income_summary: {json.dumps(income_summary, separators=(',', ':'))}
merchant_summary: {json.dumps(merchant_summary, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
query: "{query}"

Output format:
{{"chat": {{"header": "...", "entries": [...] }}, "insight_groups": [...]}}

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

    # Clean up GPT code block output
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

    return jsonify(resp_json)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
