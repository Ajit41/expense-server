import os
import json
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-pro-latest")

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get("transactions", [])
    period = data.get("period", "")
    query = data.get("query", "")
    budget = data.get("budget", 0)
    days_left = data.get("days_left", 0)
    
    prompt = f"""
You are a smart finance assistant. 
Analyze the user's transactions (as JSON) for the selected period: {period}.

Return a JSON array, where each item is:
- type: "topCategory", "savingsTip", "forecast", "upcomingBill"
- header: Short title (e.g. "Top Category: Food")
- detail: 1-2 sentences
- category: e.g. "Food", "Travel" (if relevant), empty for general
- transaction_indices: indices of transactions matching the insight (empty if not relevant)

Rules:
1. For "topCategory", return top 3 spending categories, each as a separate insight.
2. For "savingsTip", give a dynamic tip based on user's spending (not a generic one).
3. For "forecast", estimate the user's end-of-month spend and what categories need control. Use the provided 'budget' value for this month (if given), and days left.
4. For "upcomingBill", only include if at least one transaction has "isRecurring" true.
5. Do not include "User Query Response" insights.
6. Keep headers short, like "Top Category: Food" or "Forecast: ₹34,000".

Here are the user's transactions:
{json.dumps(tx_list)}

Budget for this month: {budget}
Days left in month: {days_left}
"""
    # Gemini API call
    response = model.generate_content(prompt)
    # Try to handle both response.text and response.parts[0].text
    try:
        response_text = response.text
    except AttributeError:
        response_text = response.parts[0].text

    insights = []
    try:
        insights = json.loads(response_text)
        # If for any reason the result is not a list, wrap it
        if not isinstance(insights, list):
            insights = [insights]
    except Exception as e:
        print("Error parsing Gemini response as JSON:", e)
        # fallback: show as a single insight
        insights = [{"header": "AI Response", "detail": response_text, "type": "general", "category": "", "transaction_indices": []}]
    return jsonify({"insights": insights})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
