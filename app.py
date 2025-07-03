import os
import json
from flask import Flask, request, jsonify
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)

# --- Helper Functions ---

def get_prev_period(period):
    """Given 'YYYYMM', returns previous month as 'YYYYMM'."""
    try:
        dt = datetime.strptime(period, "%Y%m")
        month = dt.month - 1
        year = dt.year
        if month == 0:
            month = 12
            year -= 1
        return f"{year}{month:02d}"
    except Exception:
        return ""

def group_by_category(transactions, period, tx_type):
    """Group transactions by category and type (0 = expense, 1 = income)."""
    summary = []
    for tx in transactions:
        if tx.get("Period") == period and tx.get("Type") == tx_type:
            found = False
            for s in summary:
                if s["category"] == tx.get("Category"):
                    s["amount"] += tx.get("Amount", 0)
                    s["count"] += 1
                    found = True
                    break
            if not found:
                summary.append({
                    "category": tx.get("Category", "Unknown"),
                    "amount": tx.get("Amount", 0),
                    "count": 1
                })
    # Format to 2 decimals
    for s in summary:
        s["amount"] = round(s["amount"], 2)
    return summary

def group_by_merchant(transactions, period, merchant_category):
    """Group transactions for a specific merchant category."""
    summary = []
    for tx in transactions:
        if tx.get("Period") == period and tx.get("Category") == merchant_category:
            found = False
            for s in summary:
                if s["merchant"] == tx.get("Transaction"):
                    s["amount"] += tx.get("Amount", 0)
                    s["count"] += 1
                    found = True
                    break
            if not found:
                summary.append({
                    "merchant": tx.get("Transaction", "Unknown"),
                    "amount": tx.get("Amount", 0),
                    "count": 1
                })
    for s in summary:
        s["amount"] = round(s["amount"], 2)
    return summary

def group_by_payment(transactions, period):
    """Group transactions by payment method for a given period."""
    summary = []
    for tx in transactions:
        if tx.get("Period") == period:
            found = False
            for s in summary:
                if s["method"] == tx.get("Method"):
                    s["amount"] += tx.get("Amount", 0)
                    s["count"] += 1
                    found = True
                    break
            if not found:
                summary.append({
                    "method": tx.get("Method", "Unknown"),
                    "amount": tx.get("Amount", 0),
                    "count": 1
                })
    for s in summary:
        s["amount"] = round(s["amount"], 2)
    return summary

# Load OpenAI API key
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    from datetime import datetime  # Redundant but safe if run in Render

    data        = request.get_json()
    tx_list     = data.get("transactions", [])
    period      = data.get("period", "")
    merchant_category = data.get("merchant_category")
    if not period:
        return jsonify({"error": "Missing required field: period"}), 400

    prev_period = get_prev_period(period)
    query       = data.get("query", "")
    budget      = data.get("budget", 0)
    days_left   = data.get("days_left", 0)
    current_month_str = datetime.now().strftime("%Y%m")

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

    expense_summary = group_by_category(filtered_tx, period, 0)
    income_summary  = group_by_category(filtered_tx, period, 1)
    merchant_summary = []
    if merchant_category:
        merchant_summary = group_by_merchant(filtered_tx, period, merchant_category)
    payment_summary = group_by_payment(filtered_tx, period)

    # ----- INSIGHT REQUEST -----
    if not query:
        prompt = f"""
You are a finance insight assistant for a personal expense tracker.

- Always use the Indian Rupee symbol (₹) for all amounts. Do NOT use "$", "Rs", or any other currency symbol.
- Never recalculate totals or counts from raw transactions. Use ONLY the provided summaries below for your analysis.
- For Payment Method, use payment_summary. For Merchant-Insights, use merchant_summary for the specified category.
- For every section, smart suggestion, notable trend, alert, or data point (including “small writing” and optional/creative insights):
    - You MUST always use this format for every value:  
      “₹{{amt}} at {{category}} ({{count}} entries)”  
      or  
      “₹{{amt}} in {{category}} ({{count}} entries)”
    - Use “entries” (plural) unless count == 1.
    - **No section, suggestion, trend, or alert is valid without this format.**
- This rule applies to Spend Timing Insights, Expense Density Map, Transaction Frequency, Zero-activity Categories, Missed Bills, Longest Expense Streak, ALL Smart Suggestions, and any optional or invented trends or alerts.
- For Card usage (where Method or Category is “Cards”), always include: “₹{{amt}} at Cards ({{count}} entries)” and suggest avoiding card interest via UPI/cash (this can be included in small writing).
- For Smart Suggestions and Other Notable Trends, you may invent new suggestions or trends if you discover other interesting, actionable patterns in the user's data.
- All insights and suggestions must be positive, user-friendly, and suggest helpful next steps or actions for the user. Never use negative or discouraging language—always encourage, empower, and guide the user toward better financial choices.
- Never repeat or duplicate insights in this period.

- **Section logic:**
  - Only show Forecast, Savings Trend, Saving Tip if period == current month ({current_month_str}).
  - High Spend must always use the required format.
  - Merchant-Insights must use merchant_summary if present.
  - Remaining Budget must always state budget left in rupees and how much spent.
  - Category Comparison must compare with previous period (if available) and mention categories and counts in format.
  - All sections and suggestions must always state data in the specified format (no exceptions).

Data available to you:
category_summary: {json.dumps(expense_summary, separators=(',', ':'))}
income_summary: {json.dumps(income_summary, separators=(',', ':'))}
payment_summary: {json.dumps(payment_summary, separators=(',', ':'))}
merchant_summary: {json.dumps(merchant_summary, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
current_month: {current_month_str}

Required insight_groups (include only if relevant data is available):
- Summary (Spending Behavior)
- Income vs Expense
- Expense Comparison (Only if both periods have matching data)
- Cash Flow
- High Spend (Top 3 categories by amount)
- Category Comparison with previous period
- Merchant-Insights (for the specified category, use merchant_summary)
- At least 4-5 Smart Suggestions (each with category, amount, and count)
- 2-3 Optional trends/alerts (optional, as described above)
- Saving Tip (if current month = period)
- Savings Trend (if current month = period)
- Remaining Budget
- Forecast (if current month = period)

Respond in this JSON format:
{{
  "insight_groups": [
    {{"header": "...", "detail": "...", "type": "...", "category": "...", "transactions":[]}},
    ...
  ]
}}
"""
    # ----- CHAT REQUEST -----
    else:
        prompt = f"""
You are a smart financial chat assistant.
Always use the Indian Rupee symbol (₹) for all amounts. Do NOT use "$", "Rs" or any other currency symbol.
Use ONLY the provided category/income/merchant/payment summaries for your analysis.
Never guess or make assumptions. If no matching data exists: return “No data for this period.”

category_summary: {json.dumps(expense_summary, separators=(',', ':'))}
income_summary: {json.dumps(income_summary, separators=(',', ':'))}
payment_summary: {json.dumps(payment_summary, separators=(',', ':'))}
merchant_summary: {json.dumps(merchant_summary, separators=(',', ':'))}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
current_month: {current_month_str}
query: "{query}"

Output format:
{{"chat": {{"header": "...", "entries": [...] }}}}
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
        # Debug log for Render logs
        print("RAW GPT RESPONSE:", response_text)
    except Exception as e:
        print("GPT API Error:", str(e))
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
        print("JSON PARSE ERROR:", str(e), "RAW:", response_text)
        return jsonify({
            "parse_error": str(e),
            "raw_response": response_text
        }), 500

    return jsonify(resp_json)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
