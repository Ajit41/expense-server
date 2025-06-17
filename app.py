import os
import json
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Initialize OpenAI client
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
You are a smart finance assistant. Analyze the user's transactions (as JSON) for the selected period: {period}.

Return a JSON OBJECT with the following keys:
- highSpendCategory: array of 2-3 top spending category insights
- anomalyDetection: array of 1-2 unusual/spiked spending messages
- savingsTip: a dynamic savings tip (string)
- forecast: a spend projection (string)
- upcomingBill: a message only if any transaction has isRecurring = true

DO NOT return markdown or explanations. Only valid JSON.

Here are the transactions:
{json.dumps(tx_list)}

Budget: ₹{budget}
Days left: {days_left}
"""

    try:
        # Make OpenAI request
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a smart finance assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        # Extract response
        response_text = completion.choices[0].message.content.strip()

        # Strip markdown if needed
        if "```json" in response_text:
            response_text = response_text.split("```json")[-1].split("```")[0].strip()
        elif response_text.startswith("```"):
            response_text = response_text.strip("```").strip()

        # Parse JSON
        insights = json.loads(response_text)

    except Exception as e:
        print("OpenAI Error:", e)
        insights = {
            "highSpendCategory": [],
            "anomalyDetection": [],
            "savingsTip": "",
            "forecast": "",
            "upcomingBill": "",
            "error": str(e)
        }

    return jsonify(insights)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
