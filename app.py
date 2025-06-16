import os
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Read Gemini API key from environment variable
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-pro-latest")

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data = request.get_json()
    tx_list = data.get('transactions', [])
    query = data.get('query', "")

    prompt = (
        "You are a smart expense assistant. Analyze these transactions and provide:\n"
        "1. Highest spending category with amount.\n"
        "2. Any anomalies.\n"
        "3. Forecast for this month.\n"
        "4. Upcoming recurring bills.\n"
        "5. One practical savings tip.\n"
    )
    if query:
        prompt += f"\nAdditionally, answer this user query: '{query}'\n"

    prompt += "\nTransactions (JSON):\n" + str(tx_list)

    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 700}
    )
    return jsonify({"insight": response.text})

if __name__ == "__main__":
    # For local dev/testing (use port 10000 for Render.com, or 8080 for others)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
