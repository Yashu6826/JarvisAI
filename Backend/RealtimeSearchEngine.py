from googlesearch import search
import google.generativeai as genai
from json import load, dump
import datetime
from dotenv import dotenv_values
import os

# --- Configuration ---
os.makedirs("Data", exist_ok=True)

Username = "Yashraj"
Assistantname = "Jarvis"

# Configure your Gemini API key
env_vars = dotenv_values(".env")
GEMINI_API_KEY = env_vars.get("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY) # Shortened for privacy

# System prompt
System = f"""Hello, I am {Username}, You are a very accurate and advanced AI chatbot named {Assistantname}.
You must provide real-time answers by analyzing the search results provided.
Strictly use the search results and real-time info for generating responses.
Answer professionally with correct grammar, punctuation, and relevance."""

# Load or initialize chat log
chatlog_path = r"Data\ChatLog.json"
if not os.path.exists(chatlog_path):
    with open(chatlog_path, "w") as f:
        dump([], f)

# Google Search function
def GoogleSearch(query):
    results = list(search(query, advanced=True, num_results=5))
    answer = "[start search results]\n"
    for result in results:
        answer += f"Title: {result.title}\nDescription: {result.description}\n\n"
    answer += "[end search results]"
    return answer

# Real-time info
def Information():
    now = datetime.datetime.now()
    return (
        "Current Date & Time Info:\n"
        f"Day: {now.strftime('%A')}\nDate: {now.strftime('%d')} {now.strftime('%B')} {now.strftime('%Y')}\n"
        f"Time: {now.strftime('%H')}:{now.strftime('%M')}:{now.strftime('%S')}\n"
    )

# Clean up output
def AnswerModifier(answer):
    return '\n'.join([line for line in answer.split('\n') if line.strip()])

# Main engine
def RealtimeSearchEngine(prompt):
    with open(chatlog_path, "r") as f:
        messages = load(f)

    # Prepare search + time + user query in one part
    search_results = GoogleSearch(prompt)
    realtime_info = Information()
    
    full_input = (
        f"{search_results}\n\n"
        f"{realtime_info}\n\n"
        f"User question: {prompt}"
    )

    # Create the full conversation for Gemini
    conversation = [
        {"role": "user", "parts": [System]},
        {"role": "user", "parts": [full_input]}
    ]

    model = genai.GenerativeModel('gemini-1.5-flash')
    chat = model.start_chat(history=conversation)

    try:
        response = chat.send_message(full_input, stream=True)
        answer = ""
        for chunk in response:
            if chunk.text:
                answer += chunk.text
        answer = answer.replace("</s", "")
    except Exception as e:
        answer = f"An error occurred: {e}"

    # Save chat history
    messages.append({"role": "user", "parts": [prompt]})
    messages.append({"role": "assistant", "parts": [answer]})
    with open(chatlog_path, "w") as f:
        dump(messages, f, indent=2)

    return AnswerModifier(answer)

# Main entry point
if __name__ == "__main__":
    while True:
        user_query = input("Enter your query: ")
        print(RealtimeSearchEngine(user_query))
