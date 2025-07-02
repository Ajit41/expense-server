import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from openai import OpenAI

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

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data        = request.get_json()
    tx_list     = data.get("transactions", [])
    period      = data.get("period", "")
    if not period:
        return jsonify({"error": "Missing required field: period"}), 400

    prev_period = get_prev_period(period)
    query       = data.get("query", "")
    budget      = data.get("budget", 0)
    days_left   = data.get("days_left", 0)

    # ✅ Filter only current and previous period transactions
    allowed_periods = {period, prev_period}
    filtered_tx = [tx for tx in tx_list if tx.get("Period") in allowed_periods]
    filtered_tx = filtered_tx[:1000]  # Token safety cap

    tx_count = len(filtered_tx)

    # ✅ Compose prompt
    if not query:
        prompt = f"""
You are a finance insight assistant for a personal expense tracker.

Use ONLY transactions where:
- Period = "{period}" → current month insights
- Period = "{prev_period}" → last month comparison

Do NOT deduplicate transactions. Every transaction must be counted as-is.

✅ Required format for all data-based messages:
  “₹{{amt}} at {{category}} ({{count}} entries)” or “₹{{amt}} in {{category}} ({{count}} entries)”
Use “entry” for 1, “entries” for >1. Never skip this format.

Strict rules:
- Sum expenses where Type = 0, income where Type = 1, only for the current Period.
- For Recurring Bill: include only where IsRecurring = true and Period = "{period}".
- Never guess, estimate, or drop duplicates.
- If no data: say clearly “No data for this period.”
- Avoid repeating categories across insight sections.
- Write friendly, helpful, and actionable insights.

Your response must include these (if data exists):
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
- Merchant-Insights (like Amazon, Big Basket, etc.)
- At least 2 Smart Suggestions (each with category, amount, and count)
- Other Notable Trends (optional)

Output format:
{{"insight_groups":[{{"header":"...", "detail":"...", "type":"...", "category":"...", "transactions":[]}}, ...]}}

Input:
transactions: {json.dumps(filtered_tx, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
"""
    else:
        prompt = f"""
You are a smart financial chat assistant.

Use ONLY:
- Period = "{period}" → for current insights
- Period = "{prev_period}" → for comparisons
Never guess or make assumptions.
If no matching data exists: return “No data for this period.”

Output format:
{{"chat": {{"header": "...", "entries": [...] }}, "insight_groups": [...]}}

Input:
transactions: {json.dumps(filtered_tx, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
query: "{query}"
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

    # 🧹 Clean up response if it’s wrapped in code blocks
    if response_text.startswith("```json"):
        response_text = response_text.removeprefix("```json").removesuffix("```").strip()
    elif response_text.startswith("```"):
        response_text = response_text.removeprefix("```").removesuffix("```").strip()

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
