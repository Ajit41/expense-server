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

    # ✅ Filter only current and previous period
    allowed_periods = {period, prev_period}
    filtered_tx = [tx for tx in tx_list if tx.get("Period") in allowed_periods]

    # ✅ Limit to avoid token overflow
    filtered_tx = filtered_tx[:1000]
    tx_count = len(filtered_tx)

    # ✅ Main prompt for insights
    if not query:
        prompt = f"""
You are an advanced finance insight assistant for a personal expense tracker app.

Use ONLY transactions where Period = "{period}" for current month insights, and Period = "{prev_period}" for comparisons.
For "total expense", sum ONLY transactions where "Type" equals 0 and "Period" is "{period}". Use "Amount" for sums and "Category" for grouping.
For "total income", sum ONLY transactions where "Type" equals 1 and "Period" is "{period}".
For previous month comparisons, use ONLY transactions with "Period" = "{prev_period}".
For Recurring Bill: include ONLY transactions where "IsRecurring" is true and Period = "{period}".

⚠️ Important formatting rule (mandatory):
- Format: “₹{{amt}} at {{category}} ({{count}} entries)” or “₹{{amt}} in {{category}} ({{count}} entries)”
- This format is required. Never skip it. Use “entry” or “entries” based on count.

Write all insights in a friendly tone. Never guess or estimate. If no data exists, say “No data for this period.”

Output must include:
- Income vs Expense
- High Spend (top 3 categories)
- Expense Comparison (only if both months have data)
- Remaining Budget (if budget > 0)
- Payment Method
- Recurring Bill
- Forecast
- Savings Tip
- Cash Flow
- At least 2 Smart Suggestions (include category, amount, and count)
- Other Notable Trends (optional)

Output ONLY this JSON:
{{"insight_groups":[...]}} 

Data received: {tx_count} transactions
Input:
transactions: {json.dumps(filtered_tx, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
"""
    else:
        # Query-based chat
        prompt = f"""
You are an advanced finance chat assistant for a personal expense tracker app.

Use ONLY transactions where Period = "{period}" for the current month.
Use ONLY transactions where Period = "{prev_period}" for previous month comparisons.
Never guess or estimate values. Always respond based only on the provided data.
If no matching data exists, reply clearly: "No data for this period."

Output format:
{{"chat": {{"header": "...", "entries": [...] }}, "insight_groups": [...]}}

Data received: {tx_count} transactions
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

    # Strip code block wrapper if present
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
