import csv
import json
import os
import re
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# --- DATA STORES ---
TIMETABLE = {
    "python": "Monday & Wednesday, 10:00 AM - 12:00 PM (LAB 302)",
    "data science": "Tuesday & Thursday, 2:00 PM - 4:00 PM (LAB 105)",
    "ai": "Friday, 9:00 AM - 11:00 AM (Seminar Hall B)",
}

CAMPUS_FAQS = {
    "internship": "3rd-year students must complete a 6-week summer internship and submit a report.",
    "attendance": "Minimum 75% attendance is mandatory to appear for semester-end exams.",
}

PORTFOLIO_FILE = "portfolio.csv"


# --- TOOLS ---
def attendance_percentage(attended: int, total: int) -> str:
    if total <= 0:
        raise ValueError("Total classes must be greater than zero.")
    if attended < 0 or attended > total:
        raise ValueError("Attended classes must be between 0 and total classes.")
    pct = round((attended / total) * 100, 2)
    status = "Eligible for exams" if pct >= 75 else "Shortage warning (Below 75%)"
    return f"Attendance: {pct}% ({status})"


def add_numbers(a: float, b: float) -> str:
    return f"The sum of {a} and {b} is {a + b}"


def lookup_timetable(subject: str) -> str:
    subject_key = subject.lower().strip()
    for key, schedule in TIMETABLE.items():
        if key in subject_key:
            return f"Timetable for {key.title()}: {schedule}"
    return (
        "No matching subject found in the timetable. Available subjects: "
        f"{', '.join(TIMETABLE.keys())}"
    )


def search_faq(topic: str) -> str:
    topic_key = topic.lower().strip()
    for key, answer in CAMPUS_FAQS.items():
        if key in topic_key:
            return f"FAQ for {key.title()}: {answer}"
    return "Information unavailable in campus FAQs. Please contact the admin office."


def read_portfolio(query: str = "") -> str:
    """Reads portfolio.csv in read-only ('r') mode and filters by query if provided."""
    if not os.path.exists(PORTFOLIO_FILE):
        return f"Portfolio file '{PORTFOLIO_FILE}' not found."

    results = []
    query_key = query.lower().strip()

    with open(PORTFOLIO_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            row_text = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
            if not query_key or query_key in row_text.lower():
                results.append(f"- {row_text}")

    if not results:
        return f"No matching portfolio entries found for '{query}'."
    return "Portfolio Details:\n" + "\n".join(results)


# --- TOOL REGISTRY ---
TOOL_REGISTRY = {
    "attendance_percentage": attendance_percentage,
    "add_numbers": add_numbers,
    "lookup_timetable": lookup_timetable,
    "search_faq": search_faq,
    "read_portfolio": read_portfolio,
}


# --- ROUTERS ---
def offline_agent_router(user_input: str) -> dict:
    text = user_input.lower()
    numbers = [int(n) for n in re.findall(r"\d+", text)]

    if "attendance" in text and len(numbers) >= 2:
        return {
            "tool": "attendance_percentage",
            "args": {"attended": numbers[0], "total": numbers[1]},
        }
    elif "attendance" in text:
        return {
            "reply": "Please provide both attended classes and total classes (e.g., 'attendance 36 out of 45')."
        }
    elif "add" in text or "sum" in text:
        if len(numbers) >= 2:
            return {"tool": "add_numbers", "args": {"a": numbers[0], "b": numbers[1]}}
        return {"reply": "Please provide two numbers to add."}
    elif "timetable" in text or "lab" in text or "when is" in text:
        return {"tool": "lookup_timetable", "args": {"subject": text}}
    elif "internship" in text or "faq" in text or "rule" in text:
        return {"tool": "search_faq", "args": {"topic": text}}
    elif any(word in text for word in ["portfolio", "bio", "cgpa", "details", "about me", "profile"]):
        clean_query = re.sub(r"\b(show|my|portfolio|bio|data|details|what is|tell me about)\b", "", text).strip()
        return {"tool": "read_portfolio", "args": {"query": clean_query}}

    return {
        "reply": "I can help with attendance calculation, addition, lab timetable, campus FAQs, and your portfolio/bio data."
    }


def live_llm_router(user_text: str) -> dict:
  from google import genai
  from google.genai import types

  api_key = os.environ.get("GEMINI_API_KEY")
  if not api_key:
    return offline_agent_router(user_text)

  try:
    client = genai.Client(api_key=api_key)

    system_prompt = """
        You are an AI tool-routing assistant. Decide which tool to call based on the user's message.
        Respond ONLY with valid JSON in one of these two formats:
        1. {"tool": "<tool_name>", "args": {<arguments>}}
        2. {"reply": "<direct text response>"}

        Available tools:
        - attendance_percentage(attended: int, total: int)
        - add_numbers(a: float, b: float)
        - lookup_timetable(subject: str)
        - search_faq(topic: str)
        - read_portfolio(query: str) -> Leave query as "" to show the full bio data/portfolio, or pass a specific keyword like "cgpa" or "college".
        """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return json.loads(response.text)
  except Exception as e:
    print("Gemini API temporary error, using offline fallback:", e)
    return offline_agent_router(user_text)

# --- AGENT EXECUTION LOOP ---
def run_agent(user_text: str, use_live_llm: bool = True) -> str:
    decision = live_llm_router(user_text) if use_live_llm else offline_agent_router(user_text)

    if "reply" in decision:
        return decision["reply"]

    tool_name = decision.get("tool")
    args = decision.get("args", {})

    if tool_name in TOOL_REGISTRY:
        try:
            return TOOL_REGISTRY[tool_name](**args)
        except Exception as e:
            return f"Error running tool '{tool_name}': {e}"

    return "Unknown tool requested."


# --- WEBSITE ROUTES ---
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    bot_reply = run_agent(user_message, use_live_llm=True)
    return jsonify({"reply": bot_reply})


if __name__ == "__main__":
    app.run(debug=True)