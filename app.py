# app.py

import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# India Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def extract_period(date_value):
    """
    Convert:
      - ISO-8601 strings (with offset)
      - Numeric ms-since-epoch
    into a YYYYMM string in IST.
    """
    # ISO-8601 string
    if isinstance(date_value, str):
        try:
            dt = datetime.fromisoformat(date_value)
            dt = dt.astimezone(IST)
            return dt.strftime("%Y%m")
        except Exception:
            pass

    # Numeric: ms since epoch
    if isinstance(date_value, (int, float)):
        try:
            dt = datetime.fromtimestamp(date_value / 1000, IST)
            return dt.strftime("%Y%m")
        except Exception:
            pass

    return None


def get_prev_period(period_str):
    """
    Given "YYYYMM", return the previous month as "YYYYMM".
    """
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
def ai_insight():
    data      = request.get_json()
    model     = data.get("model", "gpt-4o")
    tx_list   = data.get("transactions", [])
    period    = data.get("period", "")
    prev_period = get_prev_period(period)
    query     = data.get("query", "")
    budget    = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    # 1. Annotate each transaction with a computed 'Period' field
    for tx in tx_list:
        raw = tx.get("Date", tx.get("date", None))
        tx["Period"] = extract_period(raw)

    # 2. Build prompt depending on whether this is an insight-task or chat-query
    if not query:
        prompt = f"""
You are an advanced finance insight assistant for a personal expense tracker app.

Strict Data Rules:
Use ONLY transactions where "Period" matches "{period}" for all main insights.
For "total expense", sum ONLY transactions where "Type" equals 0 and "Period" is "{period}". Use "Amount" for sums and "Category" for grouping.
For "total income", sum ONLY transactions where "Type" equals 1 and "Period" is "{period}".
For previous month comparisons, use ONLY transactions with "Period" = "{prev_period}".
For Recurring Bill: include ONLY transactions where "IsRecurring" is true and "Period" = "{period}".
Always use these field names and capitalization: "Amount", "Category", "Date", "Created", "Datatype", "IsRecurring", "Method", "Note", "RecurringMode", "Reference", "Remarks1", "Transaction", "Type", "Period".
Never use or reference data from any other period.
Never guess or estimate—use only provided transaction data.
If there are no matching transactions for a category, period, or type, state clearly: "No data for this period" for that group.
All date matching must be exact.

INPUTS:
"transactions": all user transactions, each with a "Period" property ("YYYYMM").
"period": the current month ("YYYYMM").
"prev_period": previous month ("YYYYMM").
"budget": budget for the current month (if 0, ignore).
"days_left": days left in the month.

TASK:
1. Analyze only the transactions where "Period"="{period}". For previous month, use only "Period"="{prev_period}".
2. For every insight in "insight_groups" (except "Forecast", "Savings Trend", and "Cash Flow"), every "Smart Suggestion", and every "Other Notable Trend", you must embed this format in the message: "₹{{amt}} at {{category}} ({{count}} entries)" or "₹{{amt}} in {{category}} ({{count}} entries)". If a suggestion or trend applies to multiple categories, include amounts and counts for each category in the same format. Never skip this for Smart Suggestions or Other Notable Trends—these sections are only valid if they include amount, category, and count in the exact required format. Write a detailed, user-friendly message as if you are speaking directly to the user—be positive, conversational, and concise. Never leave out the amount, category, and entry count from any applicable message. If only one entry, use "entry"; if more than one, use "entries".
3. **Expense Comparison**: If no data exists for the previous month or category, state clearly "No data for this period". Do not compare if no previous data exists for the category. Do not repeat categories already present in High Spend or Smart Suggestions.
4. **High Spend**: Always show the top 3 unique categories by amount, each only once, and do not repeat categories already listed in Smart Suggestions or elsewhere.
5. **Smart Suggestions**: Each suggestion must use a unique category/amount/count not already used in High Spend, Expense Comparison, or other suggestions.
6. Never show duplicate suggestions or category/amount combos in any "insight_group" (even in Smart Suggestions).
7. For Smart Suggestions: Never suggest actions in general (like "Consider meal prepping") without tying it to the actual amount and category, e.g.: "You've spent ₹1200 at Food (8 entries) this month—try meal prepping to save more."
8. For Card Usage: Always include the actual data in the message, for example: "₹{{amt}} at Cards ({{count}} entries)" or "₹{{amt}} at Credit Card ({{count}} entries)" if relevant, and explain if high usage could lead to interest, with encouragement for UPI/cash for better control.
9. For Other Notable Trends: Always tie to specific categories and data, e.g.: "₹{{amt}} at Shopping ({{count}} entries) is 25% higher than last month. Set a 10% cut target next month."
10. For each insight or chat answer, use encouraging language for positive trends and give actionable, plain English suggestions.
11. Always include at least 5 unique Smart Suggestions, each with category, amount, and entry count, and no duplicates from other groups.
12. Optional smart trends/alerts:
   Spend Timing Insights: “80% of your monthly spending happens in the first 10 days—₹{{amt}} at {{category}} ({{count}} entries) in that time.”
   Expense Density Map: “75% of your spending is focused in just 3 categories: Food, Fuel, and Shopping—₹{{amt1}} at {{cat1}} ({{count1}}), ₹{{amt2}} at {{cat2}} ({{count2}}), ₹{{amt3}} at {{cat3}} ({{count3}}).”
   Transaction Frequency Insight: “You made 92 transactions this month—₹{{amt}} across {{category}} ({{count}} entries).”
   Merchant-Insights: “You placed 7 orders from Amazon this month (₹5,800 total).”
   Average daily spending (and if up/down)
   Budget left for key categories
   Cash Burn Rate: “Daily rate vs total balance”
   Zero-activity Categories: “You haven't spent in Health this month.”
   Notable subscriptions or upcoming bills (with days due)
   Missed Bills Alert: “Recurring items not seen this month but seen in past”
   Longest Expense Streak: “5 consecutive days with no spend" or "12-day streak of Food expenses.”
   AI Smart Suggestion: “Consider a monthly pass for coffee shops — 12 visits this month.”
   You may invent notable trends if you find other interesting, actionable patterns in the user's data. Never repeat the same in this period.
13. Example Smart Suggestions (all must include data and counts in the required format!):
   "You've made ₹3,200 at Food Delivery (12 entries)—try limiting online orders to weekends for savings."
   "₹2,400 at Subscription Services (4 entries)—review your subscriptions for unused services."
   "₹1,800 at Cab/Auto (9 entries)—consider public transport to reduce travel costs."
   "₹7,000 at Cards (5 entries)—beware of interest if not paid in full. UPI/cash may help control costs."
   "₹3,400 at Groceries (11 entries)—consider planning meals for the week to avoid impulse buys."
   "₹900 at Entertainment (2 entries)—try a no-spend Saturday for balance."
   "You made ₹2,500 at Shopping (6 entries)—set a target to cut this by 20% next month."
   You may invent new Smart Suggestions if you find other interesting, actionable patterns in the user's data.

insight_groups must include (as relevant):
- A top-level summary (type "Summary" or "Spending Behavior"), with a custom insight for this period (or state 'no data found' if there are no transactions).
- Income vs Expense
- Expense Comparison
- Remaining Budget: “You have ₹1,200 left in your ₹10,000 monthly budget.”
- High Spend: top 3 categories for this month, each with amount and entry count
- Detected anomalies (if any)
- Categories with highest change vs last month (increase/decrease %): top 3 categories
- Payment Method (with card/UPI logic as above)
- Merchant-Insights: e.g., “You placed 7 orders from Amazon this month (₹5,800 total).”
- Recurring Bill: List all transactions where "IsRecurring" is true and "Period"="{period}". If none, say 'No recurring bills for this month.'
- Forecast
- Saving Tip
- Savings Trend
- Cash Flow
- Longest Expense Streak: “5 consecutive days with no spend" or "12-day streak of Food expenses.”
- AI Smart Suggestion: “Consider a monthly pass for coffee shops — 12 visits this month.”
- At least 5 unique, data-matching Smart Suggestions
- You may invent new other notable trends if found

Format each group:
{{"header":"...","detail":"...","type":"...","category":"...","transactions":[...]}}
Output ONLY this JSON (no explanations or commentary):
{{"insight_groups":[...]}}
Input data:
transactions: {json.dumps(tx_list)}
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
For multi-month trends, use only exact periods and specify them.
Never guess, estimate, or hallucinate numbers—use only provided transaction data in the correct period(s).
If there are no matching transactions for the period or previous month, state this clearly.

INPUTS:
"transactions": all user transactions, each with a "Period" property ("YYYYMM").
"period": the current month ("YYYYMM").
"prev_period": previous month ("YYYYMM").
"budget": budget for the current month (if 0, ignore).
"days_left": days left in the month.
"query": user's chat question

TASK:
For each chat answer, write a detailed, user-friendly message as if you are speaking directly to the user—be positive, conversational, and concise.
If the query asks about a specific category, amount, time period, trend, summary, or comparison, reply with a human-friendly, data-driven answer using only the correct period(s).
Output format:
{{"chat": {{"header": "...", "entries": [...]}}, "insight_groups": [...]}}

Input data:
transactions: {json.dumps(tx_list)}
period: {period}
prev_period: {prev_period}
budget: {budget}
days_left: {days_left}
query: "{query}"
"""

    # 3. Call ChatGPT
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

    # 4. Strip code fences and parse JSON
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
