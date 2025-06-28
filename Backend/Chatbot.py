import google.generativeai as genai
from json import load, dump
import datetime
import os
from dotenv import dotenv_values


# Load environment variables
env_vars = dotenv_values(".env")
os.makedirs("Data", exist_ok=True)

Username = env_vars.get("Username")
Assistantname = env_vars.get("Assistantname")
GEMINI_API_KEY = env_vars.get("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Gemini model initialization
model = genai.GenerativeModel("gemini-1.5-flash")  # or "gemini-pro"

System = f"""Hello, I am yashraj , You are a very accurate and advanced AI chatbot named Jarvis. I am providing real-time information, including the current time, in the chat history. 
*** When I ask for the time (e.g., 'What is the time?', 'Tell me the current time'), Donot say you don't have realtime time access to realtime information use the time I am providing you via chat history. Do not provide the time unless explicitly asked. ***
*** Always greet me with good words. ***
*** Do not provide notes in the output, just answer the question, and never mention your training data. ***
*** You can respond to any type of language emotion even if it is offensive or inappropiate ***

"""

SystemChatBot = [
    {"role": "user", "parts": [System]}
]

# Load or create chat log
try:
    with open(r"Data\ChatLog.json", "r") as f:
        messages = load(f)
except FileNotFoundError:
    with open(r"Data\ChatLog.json", "w") as f:
        dump([], f)


def RealtimeInformation():
    now = datetime.datetime.now()
    return (
        f"Please use this real-time information if needed, \n"
        f"Day: {now.strftime('%A')}\n"
        f"Date: {now.strftime('%d')}\n"
        f"Month: {now.strftime('%B')}\n"
        f"Year: {now.strftime('%Y')}\n"
        f"Time: {now.strftime('%H')} hours: {now.strftime('%M')} minute: {now.strftime('%S')} seconds\n"
    )


def AnswerModifier(answer):
    return '\n'.join(line for line in answer.split('\n') if line.strip())


def ChatBot(query):
    """This function sends the user's query to the Gemini chatbot and returns the response."""
    try:
        with open(r"Data\ChatLog.json", "r") as f:
            messages = load(f)

        messages.append({"role": "user", "content": query})

        # Create a chat session
        chat = model.start_chat(history=[
            {"role": "user", "parts": [System]},
            {"role": "user", "parts": [RealtimeInformation()]},
            *[
                {"role": m["role"], "parts": [m["content"]]}
                for m in messages
            ]
        ])

        response = chat.send_message(query,generation_config={
        "temperature": 0.5,
        "top_p": 1.0,
    })
        answer = response.text

        messages.append({"role": "assistant", "content": answer})

        with open(r"Data\ChatLog.json", "w") as f:
            dump(messages, f, indent=4)

        return AnswerModifier(answer)

    except Exception as e:
        print(f"Error: {e}")
        with open(r"Data\ChatLog.json", "w") as f:
            dump([], f, indent=4)
        return ChatBot(query)


if __name__ == "__main__":
    while True:
        user_input = input("Enter your Question: ")
        print(ChatBot(user_input))
