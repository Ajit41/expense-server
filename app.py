import os
import json
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route("/", methods=["GET"])
def home():
    return "✅ AI Insight Server is running!"

@app.route("/ai-insight", methods=["POST"])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")
    query = data.get("query", "")
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)

    prompt = f"""
You are a smart finance assistant. Analyze the user's transactions for the selected period: {period}.

Return a JSON object like this:
{{
  "highSpendCategory": ["..."],
  "anomalyDetection": ["..."],
  "savingsTip": "...",
  "forecast": "...",
  "upcomingBill": "..."
}}

Rules:
1. For "highSpendCategory", give 1–3 top spending categories with amounts and explanation.
2. For "anomalyDetection", flag any unusually high or rare spends with reasoning.
3. For "savingsTip", give one personalized tip based on discretionary spend (not a generic one).
4. For "forecast", estimate end-of-month spend using budget ₹{budget} and {days_left} days left.
5. For "upcomingBill", only include if any transaction has "isRecurring": true.
6. Omit markdown/code blocks. Return only JSON.

Transactions:
{json.dumps(tx_list)}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a smart finance assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )

        result = response.choices[0].message.content.strip()

        # Clean markdown wrappers like ```json
        if result.startswith("```json"):
            result = result.removeprefix("```json").removesuffix("```").strip()
        elif result.startswith("```"):
            result = result.removeprefix("```").removesuffix("```").strip()

        json_output = json.loads(result)

        # Ensure all required fields exist
        return jsonify({
            "highSpendCategory": json_output.get("highSpendCategory", []),
            "anomalyDetection": json_output.get("anomalyDetection", []),
            "savingsTip": json_output.get("savingsTip", ""),
            "forecast": json_output.get("forecast", ""),
            "upcomingBill": json_output.get("upcomingBill", ""),
            "error": ""
        })

    except Exception as e:
        print("⚠️ AI insight error:", str(e))
        return jsonify({
            "highSpendCategory": [],
            "anomalyDetection": [],
            "savingsTip": "",
            "forecast": "",
            "upcomingBill": "",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
