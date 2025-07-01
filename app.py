from flask import Flask, request, jsonify
import os
import json
from openai import OpenAI

app = Flask(__name__)

# Initialize OpenAI client with environment variable
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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

Strict Data Rules:
- For "total expense", sum ONLY transactions where "type"=0 and the transaction date matches the specified "period" ({period}).
- For "total income", sum ONLY transactions where "type"=1 and the transaction date matches the specified "period" ({period}).
- For all insights and suggestions, include ONLY transactions for the given "period" unless explicitly stated.
- Never guess, estimate, or hallucinate numbers—always calculate from the provided transactions.
- If there are no matching transactions for the period or category, state this in the insight.
- Output JSON as a single compact line, without trailing commas or pretty print. Output must be valid for Python's json.loads().

INPUTS:
- "transactions": all user transactions for all time, as a JSON array
- "period": the current month in yyyyMM format
- "budget": budget for the current month (if 0, ignore)
- "days_left": days left in the month

TASK:
1. Use transactions and period to analyze user’s current month, compare to previous month (if available).
2. ALWAYS compute all amounts, entry counts, and categories DIRECTLY from transaction data.
3. Output only JSON with a single key: "insight_groups" (see structure below). No commentary or extra fields.
4. **Smart Suggestions:**  
   - Always include AT LEAST 5 Smart Suggestions that are actionable, personalized, and clearly supported by this user's data for the current period.
   - Suggestions can include, but are not limited to, the following (generate only if the data matches the user's behavior):
     - "You dined out 14 times this month — consider limiting to weekends to save ₹2,000."
     - "Ordering food 3× a week? Weekly meal prep could save up to ₹4,000/month."
     - "Try a grocery subscription — 9 visits this month to the same store."
     - "You took 18 cab rides this month. Public transport on weekdays could save ₹1,800."
     - "Refueling twice this month — track fuel efficiency for more savings."
     - "3 Amazon orders this week — consolidating into 1 could reduce impulse buys."
     - "Your subscriptions total ₹2,500/month. Review and cancel unused ones."
     - "You spent ₹6,000 on shopping — same as last month. Consider a 20% cut goal."
     - "Daily spending spikes on weekends — set a weekend budget to stay in control."
     - "You’ve made 85 transactions this month. Try grouping expenses to reduce clutter."
     - "Round-off savings: Saving ₹10 per transaction could build ₹800/month."
     - "Netflix, Spotify, and Prime all renew next week — budget ₹1,800 upfront."
     - "Electricity bill usually spikes mid-month — prepare for ₹1,200 soon."
     - "You always spend more after the 15th — set a mid-month reminder."
     - "Groceries exceeded ₹5,000 — try a ₹1,000/week split next month."
     - "You crossed 90% of your entertainment budget — pause subscriptions for now."
     - "Try no-spend challenges on Mondays — last month you spent ₹3,000 on them."
     - "You used credit card for 70% of purchases. Consider UPI to avoid interest."
     - "₹12,000 due on credit card next week — avoid late fees by pre-paying."
     - "Your EMI auto-debits on the 3rd — maintain ₹7,500 balance to stay safe."
   - **You may invent new Smart Suggestions if you find other interesting, actionable patterns in the user's data.**
   - Never repeat the same suggestion in this period.
   - Each Smart Suggestion must be clearly tied to a specific pattern in the user's data.

**insight_groups** must include (as relevant):
- A top-level summary or headline (type "Summary" or "Spending Behavior"), with custom insight.
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
- **At least 5 unique Smart Suggestions as described above.**
- Any other notable trends (see below).

**Optional smart trends/alerts**:
- Categories with highest change vs last month (increase/decrease %)
- Average daily spending (and if up/down)
- Budget left for key categories
- Remaining Budget: “You have ₹1,200 left in your ₹10,000 monthly budget.”
- Cash Burn Rate: “Daily rate vs total balance”
- Zero-activity Categories: “You haven't spent in Health this month.”
- Notable subscriptions or upcoming bills (with days due)
- Missed Bills Alert: “Recurring items not seen this month but seen in past”
- Longest Expense Streak: “5 consecutive days with no spend" or "12-day streak of Food expenses.”
- AI Smart Suggestion: “Consider a monthly pass for coffee shops — 12 visits this month.”
   - **You may invent notable trends if you find other interesting, actionable patterns in the user's data.**
   - Never repeat the same in this period.

**Format each group:**
{{
  "header": "...summary or insight...",
  "detail": "...full explanation (always include category, amount, entry count as applicable)...",
  "type": "...must be one of: Summary, Spending Behavior, Income vs Expense, Expense Comparison, High Spend, Saving Tip, Payment Method, Recurring Bill, Forecast, Savings Trend, Cash Flow, Anomaly, Smart Suggestion...",
  "category": "...category name if relevant...",
  "transactions": [ ...relevant transactions as JSON... ]
}}

**Output ONLY this JSON (no explanations or commentary):**
{{"insight_groups": [ ... ]}}

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

-Q: What’s my biggest expense this month?
A: Biggest expense: Food — ₹5,200 (14 entries this month)

-Q: Which category saw the most increase this month?
A: Dining Out increased by ₹1,800 (up 40% from last month)

-Q: Any spending category that dropped?
A: Fuel spend dropped by ₹900 (↓25% from last month)

-Q: What’s left in my grocery budget?
A: Grocery budget left: ₹1,200 out of ₹5,000

-Q: How many transactions this month?
A: You’ve made 74 transactions so far in this month

-Q: Any duplicate or suspicious transactions?
A: 2 potential duplicates found: ₹399 at Mobile Recharge (same amount, same day)

-Q: EMI due soon?
A: ₹7,500 EMI for ICICI Personal Loan due in 4 days

-Q: Have I crossed my monthly budget?
A: Yes — you’ve spent ₹20,200 out of your ₹20,000 budget

-Q: How much did I spend on weekends?
A: Weekend spend: ₹6,800 (34% of total expenses this month)

-Q: Which payment method did I use most?
A: UPI used in 60% of transactions, followed by Credit Card at 25%

-Q: What's my average transaction size?
A: Average transaction amount: ₹615 (from 58 entries)

-Q: What’s my spend trend in the last 7 days?
A: ₹6,100 spent in the last 7 days — peak on Saturday (₹2,300)

-Q: Did I spend more than usual this month?
A: Yes — your total spend is up 12% compared to your 3-month average

-Q: Suggest where I can save?
A: Try reducing dining out — saving 25% could save you ₹1,300

-Q: Which categories are recurring?
A: Recurring categories: Internet, Electricity, OTT Subscriptions

-Q: What are my savings this month?
A: Savings: ₹8,500 this month (21% of income)

-Q: Show me coffee shop expenses.
A: Coffee Shops: ₹2,200 (11 entries this month)

-Q: How much have I spent at Amazon?
A: Amazon purchases: ₹4,750 (5 entries this month)


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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
