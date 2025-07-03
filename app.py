import os
import json
import re
from flask import Flask, request, jsonify
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_prev_period(period):
    """Return previous month in YYYYMM format."""
    if len(period) == 6 and period.isdigit():
        year = int(period[:4])
        month = int(period[4:6])
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1
        return f"{year}{month:02d}"
    return ""

def find_txn_matches_for_period(tx_list, keyword, period):
    keyword = keyword.lower().strip()
    matches = []
    for tx in tx_list:
        if tx.get("Period") == period:
            for field in ["Transaction", "Merchant", "Title", "Category", "Method"]:
                val = tx.get(field, "")
                if keyword and keyword in str(val).lower():
                    matches.append(tx)
                    break
    return matches

def group_by_category(tx_list, period, type_value):
    summary = []
    for tx in tx_list:
        if tx.get("Period") == period and tx.get("Type") == type_value:
            cat = tx.get("Category", "Unknown")
            amt = tx.get("Amount", 0)
            found = next((item for item in summary if item["category"] == cat), None)
            if found:
                found["amount"] += amt
                found["count"] += 1
            else:
                summary.append({"category": cat, "amount": amt, "count": 1})
    for item in summary:
        item["amount"] = f"₹{item['amount']:.2f}"
    return summary

def group_by_merchant(tx_list, period, merchant_category=None):
    """
    Groups transactions by merchant (using Transaction/Merchant/Title).
    If merchant_category is specified, filters for just that merchant.
    """
    merchants = {}
    for tx in tx_list:
        if tx.get("Period") == period:
            # Use "Merchant" if available, else "Transaction", else "Title"
            m = tx.get("Merchant") or tx.get("Transaction") or tx.get("Title") or "Unknown"
            amt = tx.get("Amount", 0)
            if merchant_category:
                # If user is searching for a merchant, match partial (case-insensitive)
                if merchant_category.lower() not in m.lower():
                    continue
            if m in merchants:
                merchants[m]["amount"] += amt
                merchants[m]["count"] += 1
            else:
                merchants[m] = {"merchant": m, "amount": amt, "count": 1}
    out = []
    for m in merchants.values():
        m["amount"] = f"₹{m['amount']:.2f}"
        out.append(m)
    return out

def group_by_payment(tx_list, period):
    summary = {}
    for tx in tx_list:
        if tx.get("Period") == period:
            method = tx.get("Method", "Unknown")
            amt = tx.get("Amount", 0)
            summary.setdefault(method, 0)
            summary[method] += amt
    out = [{"method": k, "amount": f"₹{v:.2f}"} for k, v in summary.items()]
    return out

@app.route('/ai-insight', methods=['POST'])
def ai_insight():
    data        = request.get_json()
    tx_list     = data.get("transactions", [])
    period      = data.get("period", "")
    merchant_category = data.get("merchant_category")
    if not period:
        return jsonify({"error": "Missing required field: period"}), 400

    prev_period = get_prev_period(period)
    query       = (data.get("query", "") or "").strip()
    budget      = data.get("budget", 0)
    days_left   = data.get("days_left", 0)
    current_month_str = datetime.now().strftime("%Y%m")

    allowed_periods = {period, prev_period}
    filtered_tx = [tx for tx in tx_list if tx.get("Period") in allowed_periods]
    filtered_tx = filtered_tx[:1000]

    # --- Robust chat query handling ---
    if query:
        # 1. Normalize period references
        query_lower = query.lower()
        target_period = period
        compare_period = None
        if "last month" in query_lower or "previous month" in query_lower:
            compare_period = get_prev_period(period)
        if "this month" in query_lower or "current month" in query_lower:
            target_period = period
        elif "last month" in query_lower:
            target_period = get_prev_period(period)

        # 2. Look for patterns (count/total/list/compare)
        m_count = re.search(r"(how many|count|times|number of)\s+(.*?)\s+(buy|bought|order|orders|purchase|purchases|transactions?)", query_lower)
        m_total = re.search(r"(total|how much|sum|spent)\s+(.*?)\s+(on|for|in)?", query_lower)
        m_compare = re.search(r"(compare|more|less|difference|trend).*?(this|current)\s*month.*?(last|previous)\s*month", query_lower)
        m_list = re.search(r"(show|list|all)\s+(.*?)\s+(transactions?|orders?)", query_lower)

        # 3. Keyword (merchant/category/method)
        key_match = None
        if m_count:
            key_match = m_count.group(2)
        elif m_total:
            key_match = m_total.group(2)
        elif m_list:
            key_match = m_list.group(2)
        elif "upi" in query_lower:
            key_match = "upi"
        elif "card" in query_lower:
            key_match = "card"
        elif "cash" in query_lower:
            key_match = "cash"

        # 4. Handling: count
        if m_count and key_match:
            matches = find_txn_matches_for_period(filtered_tx, key_match, target_period)
            return jsonify({
                "chat": {
                    "header": f"{key_match.title()} Transactions",
                    "entries": [{
                        "header": "",
                        "detail": f"You made {len(matches)} {key_match} transactions in {target_period}."
                    }]
                }
            })

        # 5. Handling: total amount
        if m_total and key_match:
            matches = find_txn_matches_for_period(filtered_tx, key_match, target_period)
            total = sum(tx.get("Amount", 0) for tx in matches)
            return jsonify({
                "chat": {
                    "header": f"{key_match.title()} Total in {target_period}",
                    "entries": [{
                        "header": "",
                        "detail": f"Total spent for {key_match}: ₹{total:,.2f}"
                    }]
                }
            })

        # 6. Handling: comparison/trend
        if m_compare and key_match:
            tx1 = find_txn_matches_for_period(filtered_tx, key_match, period)
            tx2 = find_txn_matches_for_period(filtered_tx, key_match, prev_period)
            total1 = sum(tx.get("Amount", 0) for tx in tx1)
            total2 = sum(tx.get("Amount", 0) for tx in tx2)
            diff = total1 - total2
            trend = "increased" if diff > 0 else "decreased"
            return jsonify({
                "chat": {
                    "header": f"{key_match.title()} Comparison",
                    "entries": [{
                        "header": "",
                        "detail": f"Compared to last month, your {key_match} spending {trend} by ₹{abs(diff):,.2f} ({total1:,.2f} vs {total2:,.2f})."
                    }]
                }
            })

        # 7. Handling: list all
        if m_list and key_match:
            matches = find_txn_matches_for_period(filtered_tx, key_match, target_period)
            entry_list = [{
                "header": tx.get("Title", "") or tx.get("Transaction", ""),
                "detail": f"₹{tx.get('Amount', 0):,.2f} on {tx.get('Date', '')}"
            } for tx in matches]
            return jsonify({
                "chat": {
                    "header": f"All {key_match.title()} Transactions",
                    "entries": entry_list
                }
            })

        # 8. Fallback: No match or advice/freeform chat (Send to GPT)
        expense_summary = group_by_category(filtered_tx, period, 0)
        income_summary = group_by_category(filtered_tx, period, 1)
        merchant_summary = group_by_merchant(filtered_tx, period, merchant_category) if merchant_category else group_by_merchant(filtered_tx, period)
        payment_summary = group_by_payment(filtered_tx, period)

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
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip("`").strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:].strip("`").strip()
        try:
            resp_json = json.loads(response_text)
        except Exception as e:
            return jsonify({
                "parse_error": str(e),
                "raw_response": response_text
            }), 500

        # Normalize output for adapter
        def normalize_chat_entries(entries):
            normalized = []
            for entry in entries:
                if isinstance(entry, dict):
                    if "amount" in entry and "category" in entry:
                        normalized.append({
                            "header": entry.get("category", ""),
                            "detail": entry.get("amount", "")
                        })
                    elif "title" in entry and "value" in entry:
                        value = entry["value"]
                        if isinstance(value, list):
                            value = "\n".join(str(v) for v in value)
                        normalized.append({
                            "header": entry.get("title", ""),
                            "detail": value
                        })
                    elif "content" in entry:
                        normalized.append({
                            "header": entry.get("type", ""),
                            "detail": entry.get("content", "")
                        })
                    elif "detail" in entry and "header" in entry:
                        normalized.append({
                            "header": entry.get("header", ""),
                            "detail": entry.get("detail", "")
                        })
                    elif "text" in entry:
                        normalized.append({
                            "header": "",
                            "detail": entry.get("text", "")
                        })
                    else:
                        normalized.append({
                            "header": "",
                            "detail": ", ".join(str(v) for v in entry.values())
                        })
                else:
                    normalized.append({
                        "header": "",
                        "detail": str(entry)
                    })
            return normalized

        if "chat" in resp_json and "entries" in resp_json["chat"]:
            resp_json["chat"]["entries"] = normalize_chat_entries(resp_json["chat"]["entries"])
        return jsonify(resp_json)

    # ----------- INSIGHT FLOW -----------
    expense_summary = group_by_category(filtered_tx, period, 0)
    income_summary = group_by_category(filtered_tx, period, 1)
    merchant_summary = group_by_merchant(filtered_tx, period, merchant_category) if merchant_category else group_by_merchant(filtered_tx, period)
    payment_summary = group_by_payment(filtered_tx, period)

    if not filtered_tx or (not expense_summary and not income_summary):
        return jsonify({
            "insight_groups": [{
                "header": "No Data",
                "detail": "No transactions found for the selected period.",
                "type": "empty",
                "category": "None",
                "transactions": []
            }]
        }), 200

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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Always clean/strip code block formatting
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:].strip("`").strip()
    elif response_text.startswith("```"):
        response_text = response_text[3:].strip("`").strip()

    try:
        resp_json = json.loads(response_text)
        # Sometimes GPT returns "null"
        if not resp_json or ("insight_groups" in resp_json and not resp_json["insight_groups"]):
            raise ValueError("No insight_groups or null received")
    except Exception as e:
        return jsonify({
            "insight_groups": [{
                "header": "No Data",
                "detail": "No valid insight found. Please try again later.",
                "type": "empty",
                "category": "None",
                "transactions": []
            }]
        }), 200

    return jsonify(resp_json)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
