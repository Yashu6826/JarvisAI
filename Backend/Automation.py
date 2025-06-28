from AppOpener import close, open as appopen
from webbrowser import open as webopen
from pywhatkit import search, playonyt
from dotenv import dotenv_values
from bs4 import BeautifulSoup
from rich import print
import google.generativeai as genai
import webbrowser
import subprocess
import urllib.parse
import requests
import keyboard
import asyncio
import os
import time 
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Load environment variables
env_vars = dotenv_values(".env")
GEMINI_API_KEY = env_vars.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

classes = ["zCubwf", "hgKElc", "LTKOO sY7ric", "Z0LcW", "gsrt vk_bk FzvWSb YwPhnf", "pclqee",
           "tw-Data-text tw-text-small tw-ta", "IZ6dc", "O5uR6d LTKOO", "vlzY6d",
           "webanswers-webanswers_table_webanswers-table", "dDoNo ikb4Bb gsrt", "sXLaOe",
           "LWkfKe", "VQF4g", "qv3Wpe", "kno-rdesc", "SPZz6b"]

useragent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36'

professional_responses = [
    "Your satisfaction is my top priority; feel free to reach out if there's anything else I can help you with. ",
    "I'm at your service for any additional questions or support you may need-don't hesitate to ask."
]

messages = []

SystemChatBot = [{"role": "system", "content": f"Hello, I am yashraj, You're a content writer. You have to write content like letter"}]

def GoogleSearch(Topic):
    search(Topic)
    return True



def Content(Topic):
    def OpenNotepad(File):
        default_text_editor = 'notepad.exe'
        subprocess.Popen([default_text_editor, File])

    def ContentWriterAI(prompt):
        messages.append({"role": "user", "content": f"{prompt}"})

        # Initialize Gemini model
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "max_output_tokens": 2048,
                "temperature": 0.7,
                "top_p": 1.0,
            }
        )

        # Convert message history to Gemini-compatible format
        gemini_messages = []
        for msg in SystemChatBot + messages:
            gemini_messages.append({
                "role": "model" if msg["role"] == "assistant" else "user",
                "parts": [msg["content"]]
            })

        # Generate content with streaming
        response = model.generate_content(
            contents=gemini_messages,
            stream=True
        )

        Answer = ""
        for chunk in response:
            if chunk.text:
                Answer += chunk.text

        messages.append({"role": "assistant", "content": Answer})
        return Answer

    Topic = Topic.replace("content ", "")
    contentByAI = ContentWriterAI(Topic)

    with open(rf"Data\{Topic.lower().replace(' ', '')}.txt", "w", encoding="utf-8") as file:
        file.write(contentByAI)
        file.close()

    OpenNotepad(rf"Data\{Topic.lower().replace(' ', '')}.txt")
    return True



def YouTubeSearch(Topic):
    Url4Search = f"https://www.youtube.com/results?search_query={Topic}"
    webbrowser.open(Url4Search)
    return True

def PlayYoutube(query):
    playonyt(query)
    return True


def OpenApp(app_name, sess=None):
    if sess is None:
        sess = requests.Session()

    try:
        # Try to open the app using AppOpener
        appopen(app_name, match_closest=False, output=True, throw_error=True)
        logger.info(f"Successfully opened app '{app_name}'.")
        return True
    except Exception as e:
        logger.warning(f"App '{app_name}' not found: {e}. Attempting web search...")

        def extract_links(html):
            if not html:
                logger.debug("No HTML provided to extract links.")
                return []
            try:
                soup = BeautifulSoup(html, 'html.parser')
                # Find all <a> tags with href
                links = soup.find_all('a', href=True)
                valid_links = []
                for link in links:
                    href = link.get('href')
                    if not href:
                        continue
                    # Handle Google's /url?q= links
                    if href.startswith('/url?q='):
                        parsed = urllib.parse.urlparse(href)
                        query = urllib.parse.parse_qs(parsed.query)
                        if 'q' in query:
                            actual_url = query['q'][0]
                            if actual_url.startswith(('http://', 'https://')):
                                valid_links.append(actual_url)
                    # Handle direct URLs
                    elif href.startswith(('http://', 'https://')):
                        valid_links.append(href)
                
                # Filter and prioritize links
                app_name_lower = app_name.lower()
                prioritized_links = []
                other_valid_links = []
                for link in valid_links:
                    # Skip irrelevant Google links
                    if ('google.com' in link.lower() or
                            link.startswith('/search') or
                            'accounts.google.com' in link.lower() or
                            '/maps/' in link.lower() or
                            '/translate' in link.lower()):
                        continue
                    # Prioritize links for specific apps
                    if app_name_lower == 'playstore':
                        if 'play.google.com' in link.lower():
                            prioritized_links.insert(0, link)  # Prioritize play.google.com
                        else:
                            other_valid_links.append(link)
                    elif app_name_lower in link.lower():
                        prioritized_links.insert(0, link)  # Prioritize links with app_name
                    else:
                        other_valid_links.append(link)
                
                # Combine prioritized and other valid links
                all_links = prioritized_links + other_valid_links
                # Remove duplicates while preserving order
                seen = set()
                unique_links = [link for link in all_links if not (link in seen or seen.add(link))]
                logger.debug(f"Extracted links: {unique_links}")
                return unique_links[:1] if unique_links else []  # Return top link or empty list
            except Exception as e:
                logger.error(f"Error extracting links: {e}")
                return []

        def search_google(query):
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            try:
                time.sleep(1)  # Avoid rate-limiting
                response = sess.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Successfully fetched Google search results for '{query}'")
                    # Save HTML for debugging
                    with open(f"search_results_{app_name}.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    return response.text
                else:
                    logger.error(f"Failed to fetch search results for '{query}'. Status code: {response.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Error during Google search: {e}")
                return None

        # Fallback URLs (used only if search fails or no valid links)
        fallback_urls = {
            'facebook': 'https://www.facebook.com',
            'twitter': 'https://www.x.com',
            'youtube': 'https://www.youtube.com',
            'instagram': 'https://www.instagram.com',
            'playstore': 'https://play.google.com',
        }

        # Perform Google search
        search_query = app_name  # e.g., "playstore"
        html = search_google(search_query)
        if html:
            links = extract_links(html)
            if links:
                # Open the first valid link
                logger.info(f"Opening link: {links[0]}")
                webopen(links[0])
                return True
            else:
                logger.warning(f"No valid links found in search results for '{search_query}'.")
        else:
            logger.warning(f"Google search failed for '{search_query}'.")

        # Use fallback URL if available
        if app_name.lower() in fallback_urls:
            logger.info(f"Search failed, using fallback URL for '{app_name}': {fallback_urls[app_name.lower()]}")
            webopen(fallback_urls[app_name.lower()])
            return True
        else:
            # Try a secondary search to open the first valid link
            logger.info(f"No fallback URL for '{app_name}'. Attempting to open first valid search result...")
            html = search_google(search_query)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                links = soup.find_all('a', href=True)
                valid_links = [
                    link.get('href') for link in links
                    if link.get('href').startswith(('http://', 'https://'))
                    and 'google.com' not in link.get('href').lower()
                    and not link.get('href').startswith('/search')
                ]
                if valid_links:
                    logger.info(f"Opening first valid search result: {valid_links[0]}")
                    webopen(valid_links[0])
                    return True
                else:
                    logger.error(f"No valid links found in secondary search for '{search_query}'.")
                    return False
            else:
                logger.error(f"Secondary Google search failed for '{search_query}'.")
                return False

# OpenApp("whatsapp")


def CloseApp(app):
    if "chrome" in app:
        pass
    else:
        try:
            close(app, match_closest=True, output=True, throw_error=True)
            return True
        except:
            return False
        


def System(command):
    def mute():
        keyboard.press_and_release("volume mute")

    def unmute():
        keyboard.press_and_release("volume unmute")

    def volume_up():
        keyboard.press_and_release("volume up")

    def volume_down():
        keyboard.press_and_release("volume down")

    if command == "mute":
        mute()
    elif command == "unmute":
        unmute()
    elif command == "volume up":
        volume_up()
    elif command == "volume down":
        volume_down()

    return True

async def TranslateAndExecute(commands: list[str]):
    funcs = []

    for command in commands:
        if command.startswith("open "):
            if "open it" in command:
                pass
            if "open file" == command:
                pass
            else:
                fun = asyncio.to_thread(OpenApp, command.removeprefix("open "))
                funcs.append(fun)
        
        elif command.startswith("general "):
            pass
        elif command.startswith("realtime "):
            pass
        elif command.startswith("close "):
            fun = asyncio.to_thread(CloseApp, command.removeprefix("close "))
            funcs.append(fun)
        elif command.startswith("play "):
            fun = asyncio.to_thread(PlayYoutube, command.removeprefix("play "))
            funcs.append(fun)
        elif command.startswith("content "):
            fun = asyncio.to_thread(Content, command.removeprefix("content "))
            funcs.append(fun)
        elif command.startswith("google search "):
            fun = asyncio.to_thread(GoogleSearch, command.removeprefix("google search "))
            funcs.append(fun)
        elif command.startswith("youtube search "):
            fun = asyncio.to_thread(YouTubeSearch, command.removeprefix("youtube search "))
            funcs.append(fun)
        elif command.startswith("system "):
            fun = asyncio.to_thread(System, command.removeprefix("system "))
            funcs.append(fun)
        else:
            print(f"No Function Found, For {command}")

    results = await asyncio.gather(*funcs)

    for result in results:
        if isinstance(result, str):
            yield result
        else:
            yield result

async def Automation(commands: list[str]):
    async for result in TranslateAndExecute(commands):
        pass
    return True

if __name__ == "__main__":
    asyncio.run(Automation(["play Dooriyan"]))