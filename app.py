import os
import json
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Load OpenAI API key
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")
    query = data.get("query", "")
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    # --- DASHBOARD SUMMARY REQUEST ---
    if not query:
        prompt = f"""
You are a smart finance dashboard assistant.

Analyze the user's transactions (as JSON) for the selected period: {period}.

Return ONE JSON object, with a single key "dashboard_summary" having the following fields and grouping:

- "period_label": e.g. "This Month (Jun 25)"
- "month_comparison": {{"label": "Last month vs this month", "text": "Expense up by xx% compared to previous month"}}
- "top_high_spend": {{"label": "Top 3 High Spend", "categories": [ {{"category": "...", "amount": ..., "text": "..."}}, ... ]}}
- "anomaly_detected": {{"label": "Top Anomaly Detected", "anomalies": [ {{"category": "...", "amount": ..., "text": "..."}}, ... ]}}
- "forecast": {{"label": "This Month Forecast", "text": "..."}}
- "savings_tip": {{"label": "Saving Tip", "text": "..."}}
- "upcoming_bills": {{"label": "Upcoming Bills / Recurring Transactions", "bills": [ {{"category": "...", "amount": ..., "text": "..."}}, ... ]}}

Fill only if data is relevant, else leave as an empty list/empty string.

User's transactions:
{json.dumps(tx_list)}

Budget for this month: {budget}
Days left in month: {days_left}
"""

    # --- INSIGHT/CHAT REQUEST ---
    else:
        prompt = f"""
You are a smart finance assistant for insights and chat.

Analyze the user's transactions (as JSON) for the selected period: {period}.

If the user query is present ("{query}"):
1. Find the answer to the query and reply in a header (1 line).
2. Provide up to 10 matching transactions (full JSON details, not just indices).
3. For insights, return a list "insight_groups": each group has:
    - "header": short summary, e.g. "High spend in Food"
    - "detail": short explanation, e.g. "₹4800 spent, 20% higher than last month"
    - "type": one of: "highSpendCategory", "anomalyDetection", "forecast", "savingsTip", "upcomingBill"
    - "category": category if applicable, else empty
    - "transactions": array of matching transactions (full JSON)

The response JSON format MUST be:

{{
  "chat": {{
    "header": "...answer to user query...",
    "entries": [ ... up to 10 full transaction objects ... ]
  }},
  "insight_groups": [
    {{
      "header": "...",
      "detail": "...",
      "type": "...",
      "category": "...",
      "transactions": [ ... matching transactions ... ]
    }},
    ...
  ]
}}

Do not include explanations outside the JSON. All outputs must be inside the response JSON.

User query: "{query}"

User's transactions:
{json.dumps(tx_list)}

Budget for this month: {budget}
Days left in month: {days_left}
"""

    # ----- CALL OPENAI -----
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

    # Clean markdown blocks like ```json ... ```
    try:
        if response_text.startswith("```json"):
            response_text = response_text.removeprefix("```json").removesuffix("```").strip()
        elif response_text.startswith("```"):
            response_text = response_text.removeprefix("```").removesuffix("```").strip()
        resp_json = json.loads(response_text)
    except Exception as e:
        print("Error parsing GPT response as JSON:", e)
        # Fallback: return as string for debugging
        return jsonify({
            "parse_error": str(e),
            "raw_response": response_text
        })

    return jsonify(resp_json)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)