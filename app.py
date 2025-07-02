import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# India Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_prev_period(period_str):
    try:
        dt = datetime.strptime(period_str, "%Y%m")
        year, month = dt.year, dt.month - 1
        if month == 0:
            year -= 1
            month = 12
        prev = datetime(year, month, 1)
        return prev.strftime("%Y%m")
    except Exception:
        return None

@app.route('/ai-insight', methods=['POST'])
@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data      = request.get_json()
    tx_list   = data.get("transactions", [])
    period    = data.get("period", "")
    prev_period = get_prev_period(period)
    query     = data.get("query", "")
    budget    = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    # Only keep current and previous month transactions
    allowed_periods = {period, prev_period}
    filtered_tx = [tx for tx in tx_list if tx.get("Period") in allowed_periods]
    if not query:
        prompt = f"""
You are an advanced finance insight assistant for a personal expense tracker app.

Strict Data Rules:
1. Only analyze transactions where Period = \"{period}\" for this month, and Period = \"{prev_period}\" for last month. Ignore other data.

2. For all insight_groups (except Forecast, Savings Trend, and Cash Flow), and for every Smart Suggestion and Other Notable Trend, you MUST format values like:
   - Format: “₹{{amt}} at {{category}} ({{count}} entries)” or “₹{{amt}} in {{category}} ({{count}} entries)”
   - This is mandatory. No section is valid without this format. Always pluralize properly.

3. Expense Comparison: Only compare if data exists in both periods. If missing, say “No data for this period”. Do not duplicate categories from High Spend or Smart Suggestions.
4. High Spend: Show top 3 unique categories this month by amount. Avoid repeating these in suggestions or other sections.
5. Card Usage: If cards are used, include data like “₹{{amt}} at Cards ({{count}} entries)”, and suggest avoiding interest via UPI/cash.
6. Other Notable Trends: You may invent new Trends if you find other interesting, actionable patterns in the user's data. Example: “₹1,200 at Shopping (4 entries) is 25% higher than last month.” Never repeat the same in this period.
7. You may invent new Smart Suggestions if you find other interesting, actionable patterns in the user's data, suggestions with category, amount, and count. Do not reuse categories from insight_groups. Never repeat the same in this period.
8. All insights should be positive, user-friendly, and suggest helpful next steps. Never estimate or hallucinate. If no data, say clearly: “No data for this period.”

insight_groups must include (when data exists):
- Summary (Spending Behavior)
- Income vs Expense
- Expense Comparison
- Remaining Budget (if budget > 0)
- High Spend
- Detected anomalies (if any)
- Payment Method
- Recurring Bill (IsRecurring = true, Period = \"{period}\")
- Forecast (show only current month = period)
- Saving Tip
- Savings Trend
- Cash Flow
- Longest Expense Streak
- Merchant-Insights (e.g., Amazon, Flipkart)
- At least 1 unique Smart Suggestions
- Other Notable Trend if any

Format each group:
{{"header":"...","detail":"...","type":"...","category":"...","transactions":[...]}}
Output ONLY this JSON (no explanations or commentary):
{{"insight_groups":[...]}}

Input data:
transactions: {json.dumps(filtered_tx)}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
"""
    else:
        prompt = f"""
You are an advanced finance chat assistant for a personal expense tracker app.

Strict Data Rules:
Use ONLY transactions where "Period" matches "{period}" for main answers.
For previous month comparisons, use ONLY transactions with "Period"="{prev_period}".
Never guess or estimate.
If no matching transactions, say: "No data for this period."

Output format:
{{"chat": {{"header": "...", "entries": [...]}}, "insight_groups": [...]}}

Input data:
transactions: {json.dumps(filtered_tx)}
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
                {"role": "user",   "content": prompt}
            ],
            temperature=0.65
        )
        response_text = chat_completion.choices[0].message.content
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
