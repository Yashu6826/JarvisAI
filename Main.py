from Frontend.GUI import (
    GraphicalUserInterface,
    SetAssistantStatus,
    ShowTextToScreen,
    TempDirectoryPath,
    SetMicrophoneStatus,
    GetMicrophoneStatus,
    AnswerModifier,
    QueryModifier,
    GetAssistantStatus
)
from Backend.Model import FirstLayerDMM
from Backend.RealtimeSearchEngine import RealtimeSearchEngine
from Backend.Automation import Automation
from Backend.SpeechToText import SpeechRecognition
from Backend.Chatbot import ChatBot
from Backend.TextToSpeech import TextToSpeech
from asyncio import run
from time import sleep
import subprocess
import threading
import sys
import json
import os
import logging

# Configure logging
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

Username = "yashraj"
Assistantname = "Jarvis"
DefaultMessage = f'''{Username}: Hello {Assistantname}, How are you?
{Assistantname}: Welcome {Username} sir. How are you today. How may I help you.?'''
Functions = ["open","close","play","system","content","google search","youtube search"]
subprocess_list=[]

def ShowDefaultChatIfNoChats():
    chatlog_path = os.path.abspath(os.path.join("Data", "ChatLog.json"))
    database_path = TempDirectoryPath('Database.data')
    responses_path = TempDirectoryPath('Responses.data')

    logger.info(f"Checking ChatLog.json at: {chatlog_path}")
    logger.info(f"Database.data path: {database_path}")
    logger.info(f"Responses.data path: {responses_path}")

    try:
        with open(chatlog_path, "r", encoding='utf-8') as file:
            content = file.read()
            logger.info(f"ChatLog.json content length: {len(content)}")
            logger.info(f"ChatLog.json content: {content[:100]}...")  # Log first 100 chars
            if len(content.strip()) == 0 or content.strip() in ["{}", "[]"]:
                logger.info("ChatLog.json is empty or nearly empty, writing default message")
                # Ensure directories exist
                os.makedirs(os.path.dirname(database_path), exist_ok=True)
                os.makedirs(os.path.dirname(responses_path), exist_ok=True)
                # Write to Responses.data directly
                with open(responses_path, 'w', encoding='utf-8') as file:
                    file.write(DefaultMessage)
                    logger.info(f"Wrote default message to {responses_path}")
                # Clear Database.data
                with open(database_path, 'w', encoding='utf-8') as file:
                    file.write("")
                    logger.info(f"Cleared {database_path}")
    except FileNotFoundError:
        logger.warning(f"ChatLog.json not found at {chatlog_path}, creating with default message")
        os.makedirs(os.path.dirname(chatlog_path), exist_ok=True)
        with open(chatlog_path, "w", encoding='utf-8') as file:
            file.write("[]")  # Initialize empty JSON array
        with open(responses_path, 'w', encoding='utf-8') as file:
            file.write(DefaultMessage)
            logger.info(f"Wrote default message to {responses_path}")
        with open(database_path, 'w', encoding='utf-8') as file:
            file.write("")
            logger.info(f"Cleared {database_path}")
    except Exception as e:
        logger.error(f"Error in ShowDefaultChatIfNoChats: {e}")

def ReadChatLogJson():
    chatlog_path = os.path.abspath(os.path.join("Data", "ChatLog.json"))
    logger.info(f"Reading ChatLog.json from: {chatlog_path}")
    try:
        with open(chatlog_path, 'r', encoding='utf-8') as file:
            chatlog_data = json.load(file)
            logger.info(f"Successfully read ChatLog.json: {len(chatlog_data)} entries")
            return chatlog_data
    except FileNotFoundError:
        logger.warning(f"ChatLog.json not found, returning empty list")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in ChatLog.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Error reading ChatLog.json: {e}")
        return []

def ChatLogIntegration():
    logger.info("Starting ChatLogIntegration")
    json_data = ReadChatLogJson()
    formatted_chatlog = ""
    for entry in json_data:
        message = entry["parts"][0] if entry.get("parts") else ""
        if entry["role"] == "user":
            formatted_chatlog += f"User: {message}\n"
        elif entry["role"] == "assistant":
            formatted_chatlog += f"Assistant: {message}\n"
    formatted_chatlog = formatted_chatlog.replace("User", Username + " ")
    formatted_chatlog = formatted_chatlog.replace("Assistant", Assistantname + " ")
    
    database_path = TempDirectoryPath('Database.data')
    logger.info(f"Writing to Database.data: {database_path}")
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    with open(database_path, 'w', encoding='utf-8') as file:
        file.write(AnswerModifier(formatted_chatlog))
        logger.info(f"Wrote formatted chatlog to {database_path}")

def ShowChatsOnGUI():
    database_path = TempDirectoryPath('Database.data')
    responses_path = TempDirectoryPath('Responses.data')
    logger.info(f"Reading Database.data from: {database_path}")
    logger.info(f"Writing to Responses.data: {responses_path}")
    
    try:
        with open(database_path, "r", encoding='utf-8') as file:
            data = file.read()
            logger.info(f"Database.data content length: {len(data)}")
            if len(data.strip()) > 0:
                lines = data.split('\n')
                result = '\n'.join(lines)
                os.makedirs(os.path.dirname(responses_path), exist_ok=True)
                with open(responses_path, "w", encoding='utf-8') as file:
                    file.write(result)
                    logger.info(f"Copied content to Responses.data")
                ShowTextToScreen(result)
                logger.info("Updated GUI with Responses.data content")
            else:
                logger.info("Database.data is empty, checking for default message")
                with open(responses_path, "r", encoding='utf-8') as file:
                    current_content = file.read()
                    if current_content.strip() == "":
                        logger.info("Responses.data is empty, writing default message")
                        with open(responses_path, "w", encoding='utf-8') as file:
                            file.write(DefaultMessage)
                        ShowTextToScreen(DefaultMessage)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        with open(responses_path, "w", encoding='utf-8') as file:
            file.write(DefaultMessage)
            logger.info(f"Wrote default message to {responses_path}")
        ShowTextToScreen(DefaultMessage)
    except Exception as e:
        logger.error(f"Error in ShowChatsOnGUI: {e}")
        ShowTextToScreen(DefaultMessage)

def InitialExecution():
    logger.info("Starting InitialExecution")
    SetMicrophoneStatus("False")
    responses_path = TempDirectoryPath('Responses.data')
    logger.info(f"Writing default message to {responses_path}")
    os.makedirs(os.path.dirname(responses_path), exist_ok=True)
    with open(responses_path, 'w', encoding='utf-8') as file:
        file.write(DefaultMessage)
    
    ShowTextToScreen(DefaultMessage)
    TextToSpeech(DefaultMessage.split(f"{Assistantname}: ")[1])
    # Speak assistant's part
    logger.info("Completed InitialExecution")

InitialExecution()

def MainExecution():
    TaskExection = False
    ImageExecution = False
    ImageGenerationQuery = ""

    while GetMicrophoneStatus() == "True":
        SetAssistantStatus("Listening...")
        Query = SpeechRecognition()
        if Query == "":
            continue  # Skip empty queries and listen again
        ShowTextToScreen(f"{Username}: {Query}")
        SetAssistantStatus("Thinking... ")
        Decision = FirstLayerDMM(Query)
        print("")
        print(f"Decision : {Decision}")
        print("")

        G = any([i for i in Decision if i.startswith("general")])
        R = any([i for i in Decision if i.startswith("realtime")])


        Mearged_query = " and ".join(
            [" ".join(i.split()[1:]) for i in Decision if i.startswith("general") or i.startswith("realtime")]
        )

        for queries in Decision:
            if "generate " in queries:
                ImageGenerationQuery = str(queries)
                ImageExecution = True

        
            if TaskExection == False:
                if any(queries.startswith(func) for func in Functions):
                    run(Automation(list(Decision)))
                    

        if ImageExecution == True:
            file_path = os.path.abspath(os.path.join("Frontend", "Files", "ImageGeneration.data"))
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            logging.info(f"Writing to {file_path}: {ImageGenerationQuery},True")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(f"{ImageGenerationQuery},True")
            
            try:
                image_gen_path = os.path.abspath(os.path.join("Backend", "ImageGeneration.py"))
                logging.info(f"Starting subprocess: {sys.executable} {image_gen_path}")
                p1 = subprocess.Popen(
                    [sys.executable, image_gen_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False
                )
                subprocess_list.append(p1)
                stdout, stderr = p1.communicate(timeout=30)
                if p1.returncode != 0:
                    logging.error(f"ImageGeneration.py failed with error: {stderr}")
                else:
                    logging.info(f"ImageGeneration.py output: {stdout}")
            except subprocess.TimeoutExpired:
                logging.error("ImageGeneration.py timed out")
                p1.terminate()
            except Exception as e:
                logging.error(f"Error starting ImageGeneration.py: {e}")

        if G and R or R:
            SetAssistantStatus("Searching... ")
            Answer = RealtimeSearchEngine(QueryModifier(Mearged_query))
            ShowTextToScreen(f"{Assistantname}: {Answer}")
            SetAssistantStatus("Answering... ")
            TextToSpeech(Answer)
        
        else:
            for Queries in Decision:
                if "general" in Queries:
                    SetAssistantStatus("Thinking... ")
                    QueryFinal = Queries.replace("general ", "")
                    Answer = ChatBot(QueryModifier(QueryFinal))
                    ShowTextToScreen(f"{Assistantname}: {Answer}")
                    SetAssistantStatus("Answering... ")
                    TextToSpeech(Answer)
                elif "realtime" in Queries:
                    SetAssistantStatus("Searching... ")
                    QueryFinal = Queries.replace("realtime ", "")
                    Answer = RealtimeSearchEngine(QueryModifier(QueryFinal))
                    ShowTextToScreen(f"{Assistantname}: {Answer}")
                    SetAssistantStatus("Answering... ")
                    TextToSpeech(Answer)
                elif "exit" in Queries:
                    QueryFinal = "Okay, Bye!"
                    Answer = ChatBot(QueryModifier(QueryFinal))
                    ShowTextToScreen(f"{Assistantname}: {Answer}")
                    SetAssistantStatus("Answering... ")
                    TextToSpeech(Answer)
                    SetAssistantStatus("Answering... ")
                    SetMicrophoneStatus("False")
                    os._exit(1)

def FirstThread():
    while True:
        CurrentStatus = GetMicrophoneStatus()
        # print(f"[DEBUG] Mic Status: {CurrentStatus}")
        if CurrentStatus == "True":
            print("[DEBUG] Starting MainExecution()")
            MainExecution()
        else:
            AIStatus = GetAssistantStatus()
            if "Available..." not in AIStatus:
                SetAssistantStatus("Available...")
            sleep(0.1)

def SecondThread():
    GraphicalUserInterface()

if __name__ == "__main__":
    thread2 = threading.Thread(target= FirstThread,daemon= True)
    thread2.start()
    SecondThread()


