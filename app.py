from flask import Flask

app = Flask(__name__)

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")
    query = data.get("query", "")
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    # ----------- INSIGHT PROMPT (no query) -----------
    if not query:
        prompt = f"""
You are an advanced finance insight assistant for a personal expense tracker app.

INPUTS:
- "transactions": all user transactions for all time, as a JSON array
- "period": the current month in yyyyMM format
- "budget": budget for the current month (if 0, ignore)
- "days_left": days left in the month

TASK:
1. Use transactions and period to analyze user’s current month, compare to previous month (if available).
2. ALWAYS compute all amounts, entry counts, and categories DIRECTLY from transaction data.
3. Output only JSON with a single key: "insight_groups" (see structure below). No commentary or extra fields.

**insight_groups** must include (as relevant):
- A top-level summary or headline (type "Summary" or "Spending Behavior"), with custom insight. Example: "Groceries account for 28% of your spend this month." or "Weekend spending is double weekdays."
- Income vs Expense
- Expense Comparison
- High Spend: Top 3 categories for this month, as "High Spend: [Category] (₹[amount], [entry count] entries)..."
- Detected anomalies: “Unusual spend detected: ₹xxxx at [category] (₹[amount], [entry count] entries)...”
- Saving Tip: Based on highest category, suggest 25% savings (amount & entries shown)
- Payment Method: Top 2 payment methods; if "card" is highest, issue alert about interest.
- Recurring Bill: List all this month’s recurring bills (isRecurring==true)
- Forecast: Project month-end spend (show if above/below budget)
- Savings Trend: Savings up/down compared to last month
- Cash Flow: Income/expense ratio
- Any other notable trends (see below).

**Optional smart trends/alerts**:
- Categories with highest change vs last month (increase/decrease %)
- Average daily spending (and if up/down)
- Budget left for key categories
- Notable subscriptions or upcoming bills (with days due)
- AI Smart Suggestion: “Consider a monthly pass for coffee shops — 12 visits this month.”

**Format each group:**
{{
  "header": "...summary or insight...",
  "detail": "...full explanation (always include category, amount, entry count as applicable)...",
  "type": "...must be one of: Summary, Spending Behavior, Income vs Expense, Expense Comparison, High Spend, Saving Tip, Payment Method, Recurring Bill, Forecast, Savings Trend, Cash Flow, Anomaly, Smart Suggestion...",
  "category": "...category name if relevant...",
  "transactions": [ ...relevant transactions as JSON... ]
}}

**Output ONLY this JSON (no explanations or commentary):**
{{
  "insight_groups": [ ... ]
}}

Use only actual data. Do not hallucinate or invent values.

Input data:
transactions: {json.dumps(tx_list)}
budget: {budget}
days_left: {days_left}
period: {period}
"""
    # ----------- CHAT PROMPT (with query) -----------
    else:
        prompt = f"""
You are an advanced finance chat assistant for a personal expense tracker app.

INPUTS:
- "transactions": all user transactions for all time, as JSON array
- "period": the current month in yyyyMM format
- "budget": budget for the current month (if 0, ignore)
- "days_left": days left in the month
- "query": user's chat question

TASK:
- If the query asks about a specific category, amount, time period, trend, summary, or comparison, reply with a human-friendly, data-driven answer.
- Always base your answer on transaction data for the specified period/category. 
- Never invent values. Compute all values (amounts, counts, dates, etc) directly from the input transactions.
- For every query, output **only** the JSON format below.

**Output format:**
{{
  "chat": {{
    "header": "...summary answer (always include category, amount, entry count, and period info if relevant)...",
    "entries": [ ...up to 10 matching transactions as JSON... ]
  }},
  "insight_groups": [ ...as above, for additional relevant insights... ]
}}

**Example Queries and Responses:**
- Q: How much did I spend on food this month?
  A: Food: ₹4,350 (12 entries this month)

- Q: How much groceries in June?
  A: Groceries: ₹2,800 (6 entries in 202406)

- Q: Total expenses last month?
  A: Total expenses in June: ₹24,000 (65 entries)

- Q: My top category this month?
  A: Top category: Food (₹4,350, 12 entries)

- Q: What are my recurring bills?
  A: 3 recurring bills this month: Internet (₹1,000), Mobile (₹400), Netflix (₹999)

- Q: What is my average daily spend?
  A: Average daily spend this month: ₹700

- Q: Card spend vs UPI spend?
  A: Card: ₹2,000 (5 entries), UPI: ₹4,100 (13 entries)

- Q: Am I overspending compared to last month?
  A: Yes, your total expenses increased by 18% compared to last month.

- Q: Unusual spend?
  A: Unusual spend detected: ₹3,200 at Electronics Store (4x usual, 2 entries this month)

- Q: Upcoming subscription?
  A: Netflix subscription due in 3 days (₹999)

- Q: Forecast this month?
  A: Projected month-end spend: ₹15,400 (₹1,900 over your budget)

- Q: Savings trend?
  A: Savings improved by ₹1,200 compared to last month.

- Q: Income vs expense?
  A: Income: ₹40,000, Expenses: ₹31,700, Savings: ₹8,300

- Q: What if I ask something not in the data?
  A: Respond politely: "No data found for your request."

**INSTRUCTION:**
- Always reply with the correct JSON structure, no commentary.
- Your "header" in "chat" should sound natural, just like the examples above, and include category, amount, entry count, and period info where appropriate.

Input data:
transactions: {json.dumps(tx_list)}
budget: {budget}
days_left: {days_left}
period: {period}
query: "{query}"
"""

    try:
        chat_completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a smart finance assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.65
        )
        response_text = chat_completion.choices[0].message.content
    except Exception as e:
        print("OpenAI error:", e)
        return jsonify({"error": str(e)})

    try:
        if response_text.startswith("```json"):
            response_text = response_text.removeprefix("```json").removesuffix("```").strip()
        elif response_text.startswith("```"):
            response_text = response_text.removeprefix("```").removesuffix("```").strip()
        resp_json = json.loads(response_text)
    except Exception as e:
        print("Error parsing GPT response as JSON:", e)
        return jsonify({
            "parse_error": str(e),
            "raw_response": response_text
        })

    return jsonify(resp_json)
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))  # Railway or Render will set PORT
    app.run(host="0.0.0.0", port=port)
