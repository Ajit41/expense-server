from flask import Flask, request, jsonify
import os
import json
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def extract_period(date_str):
    """Extract YYYYMM period from date string like 'June 28, 2025 at 12:00:00 AM UTC+5:30'."""
    try:
        date_clean = str(date_str).split(" UTC")[0]
        dt = datetime.strptime(date_clean.strip(), "%B %d, %Y at %I:%M:%S %p")
        return dt.strftime("%Y%m")
    except Exception:
        try:
            # If it's an int timestamp (ms)
            if isinstance(date_str, (int, float)):
                dt = datetime.utcfromtimestamp(date_str / 1000)
                return dt.strftime("%Y%m")
        except Exception:
            pass
    return None

def get_prev_period(period_str):
    """Given YYYYMM as string, return previous month as YYYYMM."""
    try:
        dt = datetime.strptime(period_str, "%Y%m")
        if dt.month == 1:
            prev_dt = dt.replace(year=dt.year-1, month=12)
        else:
            prev_dt = dt.replace(month=dt.month-1)
        return prev_dt.strftime("%Y%m")
    except Exception:
        return None

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")  # e.g., "202506"
    query = data.get("query", "")
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    # Annotate each transaction with a computed 'period' field
    for tx in tx_list:
        date_str = tx.get("date", "")
        if isinstance(date_str, (int, float)):
            dt = datetime.utcfromtimestamp(date_str / 1000)
            tx['period'] = dt.strftime("%Y%m")
        else:
            tx['period'] = extract_period(date_str)

    prev_period = get_prev_period(period)

    # ----------- INSIGHT PROMPT (no query) -----------
    if not query:
        prompt = f"""
You are an advanced finance insight assistant for a personal expense tracker app.

Strict Data Rules:
- Use ONLY transactions where 'period' matches the specified period ({period}) for all main insights.
- For "total expense", sum ONLY transactions with "type"=0 and period={period}.
- For "total income", sum ONLY transactions with "type"=1 and period={period}.
- For previous month comparisons, use ONLY transactions with period={prev_period}.
- For multi-month forecasts/trends, you may use 1–3 previous months ({prev_period} and earlier), but specify which periods you used.
- Never use or reference data from any other period.
- Never guess, estimate, or hallucinate numbers—use only provided transaction data in the correct period(s).
- If there are no matching transactions for the period or previous month, state this clearly in the insight.
- All date matching must be exact.

INPUTS:
- "transactions": all user transactions, each with a 'period' property ("YYYYMM").
- "period": the current month ("YYYYMM").
- "prev_period": previous month ("YYYYMM").
- "budget": budget for the current month (if 0, ignore).
- "days_left": days left in the month.

TASK:
1. Analyze only the transactions where period={period}. For previous month, use only period={prev_period}. For multi-month insights, specify which periods.
2. For each insight or chat answer, write a detailed, user-friendly message as if you are speaking directly to the user—be positive, conversational, and concise.
   - Use encouraging language for positive trends.
   - Give clear, actionable suggestions ("You could save ₹2,000 next month by limiting dining out to weekends.").
   - Always use plain English, showing amounts, entry counts, and category names in context.
   - For summaries and trends, explain what changed and what it means for the user.
   - For negative trends, give a positive nudge or an idea for improvement.
3. Always include at least 5 unique Smart Suggestions, based only on this period's data, with category, amount, and entry count. Each Smart Suggestion must be clearly tied to a specific pattern in the user's data. Never repeat the same suggestion in this period.
4. **Optional smart trends/alerts**: 
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
   - You may invent notable trends if you find other interesting, actionable patterns in the user's data. Never repeat the same in this period.
5. Example Smart Suggestions for inspiration (generate only if the data matches the user's behavior):
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
   - You may invent new Smart Suggestions if you find other interesting, actionable patterns in the user's data.

**insight_groups** must include (as relevant):
- A top-level summary (type "Summary" or "Spending Behavior"), with a custom insight for this period (or state 'no data found' if there are no transactions).
- Income vs Expense (see above for message)
- Expense Comparison
- High Spend: top 3 categories for this month, each with amount and entry count
- Detected anomalies (if any)
- Saving Tip
- Payment Method
- Recurring Bill
- Forecast
- Savings Trend
- Cash Flow
- At least 5 unique, data-matching Smart Suggestions
- Any other notable trends if found

**Format each group:**
{{"header":"...","detail":"...","type":"...","category":"...","transactions":[...]}}
**Output ONLY this JSON (no explanations or commentary):**
{{"insight_groups":[...]}}

Input data:
transactions: {json.dumps(tx_list)}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
"""
    # ----------- CHAT PROMPT (with query) -----------
    else:
        prompt = f"""
You are an advanced finance chat assistant for a personal expense tracker app.

Strict Data Rules:
- Use ONLY transactions where 'period' matches the specified period ({period}) for main answers.
- For previous month comparisons, use ONLY transactions with period={prev_period}.
- For multi-month trends, use only exact periods and specify them.
- Never guess, estimate, or hallucinate numbers—use only provided transaction data in the correct period(s).
- If there are no matching transactions for the period or previous month, state this clearly.

INPUTS:
- "transactions": all user transactions, each with a 'period' property ("YYYYMM").
- "period": the current month ("YYYYMM").
- "prev_period": previous month ("YYYYMM").
- "budget": budget for the current month (if 0, ignore).
- "days_left": days left in the month.
- "query": user's chat question

TASK:
- For each chat answer, write a detailed, user-friendly message as if you are speaking directly to the user—be positive, conversational, and concise.
- If the query asks about a specific category, amount, time period, trend, summary, or comparison, reply with a human-friendly, data-driven answer using only the correct period(s).
- Output format:
{{"chat": {{"header": "...", "entries": [ ...transactions... ]}}, "insight_groups": [ ... ]}}

Input data:
transactions: {json.dumps(tx_list)}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
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
