import re
import time
import asyncio
import datetime
import wmi
import pywhatkit
import wikipedia
import webbrowser
import subprocess
import psutil
import pygame.mixer
import requests
from core.config import TTS_AVAILABLE, GEMINI_AVAILABLE, VOLUME_CONTROL_AVAILABLE, MEMORY_LIMIT, context_memory, loop, \
    interrupt_flag, APP_PATHS, INTENT_CATEGORIES

try:
    import edge_tts
except ImportError:
    pass
try:
    import google.generativeai as genai
except ImportError:
    pass
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
except ImportError:
    pass


def filter_text(text: str) -> str:
    """Clean text for TTS by removing markdown and special characters."""
    text = re.sub(r'\*\*.*?\*\*|\*.*?\*|`.*?`', lambda m: m.group(0)[1:-1], text)
    text = re.sub(r'[\n\r]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9.,!?\'" ]', '', text)
    return ' '.join(text.split())


async def text_to_speech(text: str, callback=None) -> None:
    """Convert text to speech using edge-tts."""
    global is_speaking
    if not TTS_AVAILABLE:
        if callback:
            callback(f"TTS: {text}")
        return

    try:
        clean_text = filter_text(text)
        voice = "en-US-JennyNeural"
        tts = edge_tts.Communicate(clean_text, voice, rate="+15%")
        audio_file = f"response_{int(time.time())}.mp3"
        await tts.save(audio_file)
        is_speaking = True
        interrupt_flag.clear()
        if callback:
            callback(" ")
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if interrupt_flag.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.1)
        is_speaking = False
        try:
            os.remove(audio_file)
        except:
            pass
    except Exception as e:
        if callback:
            callback(f"TTS Error: {text}")


def ask_gemini(prompt: str) -> str:
    """Query Gemini AI model with context-aware prompt."""
    if not GEMINI_AVAILABLE:
        return "Gemini AI is not available. Please install google-generativeai and add your API key."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        system_prompt = """
            You are an advanced, context-aware AI assistant named Echo, designed to deliver precise, insightful, and efficient responses. Your primary goal is to provide clear, intelligent, and engaging answers while maintaining brevity and relevance. Follow these principles:
            - Adapt to Context & Mood: Align your tone with the user's mood and the nature of the conversation—whether casual, professional, or highly technical.
            - Be Concise, Yet Complete: Deliver well-structured responses that are neither too short nor unnecessarily verbose. Prioritize clarity and depth without over-explaining.
            - No Redundancy: Avoid repeating information or your name ("Echo") unless necessary for clarity or emphasis.
            - Ask Smart Questions: If a query lacks clarity, request precise details with a brief, targeted question.
            - Ensure Logical Flow: Keep responses interconnected, ensuring a seamless and engaging dialogue.
            - Encourage Exploration: When relevant, subtly suggest related ideas or next steps to enhance the user's understanding.
            - Prioritize Accuracy & Relevance: Always provide well-reasoned, factual, and contextually appropriate responses.
            Your mission: Deliver an exceptional user experience with every interaction. Avoid starting responses with "Echo" or self-referential phrases unless explicitly asked about your identity.
        """
        memory_context = "\n".join(context_memory)
        full_prompt = f"{system_prompt}\n{memory_context}\nUser: {prompt}"
        response = model.generate_content(full_prompt)
        formatted_response = response.text.strip() if response.text else "I couldn't process that."
        context_memory.append(f"User: {prompt}\nEcho: {formatted_response}")
        if len(context_memory) > MEMORY_LIMIT:
            context_memory.pop(0)
        return formatted_response
    except Exception as e:
        return f"I'm having trouble connecting to my AI service. Error: {str(e)}"


def get_day_date() -> str:
    """Return the current day and date."""
    return datetime.datetime.now().strftime("%A, %B %d, %Y")


def close_application(app_name: str) -> bool:
    """Close the specified application."""
    closed = False
    for proc in psutil.process_iter():
        try:
            if app_name.lower() in proc.name().lower():
                proc.terminate()
                closed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return closed


def set_volume(level: int) -> bool:
    """Set system volume to the specified level."""
    if not VOLUME_CONTROL_AVAILABLE:
        return False
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMasterVolumeLevelScalar(level / 100, None)
        return True
    except:
        return False


def set_brightness(level: int) -> bool:
    """Set screen brightness to the specified level."""
    try:
        c = wmi.WMI(namespace='wmi')
        methods = c.WmiMonitorBrightnessMethods()[0]
        methods.WmiSetBrightness(level, 0)
        return True
    except Exception:
        return False


def identify_intent(command: str) -> str:
    """Identify the intent of the user's command."""
    command_lower = command.lower()
    for intent, keywords in INTENT_CATEGORIES.items():
        if any(keyword in command_lower for keyword in keywords):
            return intent
    return "ai_chat"


def duckduckgo_search(query: str) -> str:
    """Perform a search using DuckDuckGo API."""
    url = f"http://api.duckduckgo.com/?q={query}&format=json&no_redirect=1"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        elif data.get("RelatedTopics") and data["RelatedTopics"]:
            if data["RelatedTopics"][0].get("Text"):
                return data["RelatedTopics"][0]["Text"]
        return None
    except Exception:
        return None


def process_command(command: str) -> str:
    """Process voice commands and return appropriate responses."""
    try:
        if "play" in command and any(word in command for word in ["song", "music", "on youtube", "youtube"]):
            song = command.replace("play", "").replace("song", "").replace("music", "").replace("on youtube",
                                                                                                "").replace("youtube",
                                                                                                            "").strip()
            if song:
                try:
                    pywhatkit.playonyt(song)
                    return f"Playing {song} on YouTube"
                except:
                    return f"Sorry, I couldn't play {song}"
            return "What would you like me to play?"
        elif "time" in command:
            time_now = datetime.datetime.now().strftime('%I:%M %p')
            return f"The current time is {time_now}"
        elif "date" in command or "day" in command:
            return f"Today is {get_day_date()}"
        elif any(phrase in command for phrase in ["tell me about", "who is", "what is", "explain"]):
            subject = command
            for phrase in ["tell me about", "who is", "what is", "explain"]:
                subject = subject.replace(phrase, "").strip()
            if subject:
                try:
                    info = wikipedia.summary(subject, sentences=2)
                    return info
                except wikipedia.exceptions.DisambiguationError:
                    return f"There are multiple results for {subject}. Can you be more specific?"
                except wikipedia.exceptions.PageError:
                    return f"I couldn't find information about {subject}"
            return "What would you like to know about?"
        elif "open" in command:
            app_or_site = command.replace("open", "").strip()
            if app_or_site in APP_PATHS:
                try:
                    subprocess.Popen(APP_PATHS[app_or_site])
                    return f"Opening {app_or_site}"
                except:
                    return f"I couldn't open {app_or_site}"
            else:
                try:
                    if "." in app_or_site or any(
                            site in app_or_site for site in ["google", "youtube", "facebook", "twitter"]):
                        if not app_or_site.startswith("http"):
                            app_or_site = f"https://{app_or_site}" if "." in app_or_site else f"https://www.{app_or_site}.com"
                        webbrowser.open(app_or_site)
                        return f"Opening {app_or_site} in browser"
                    else:
                        webbrowser.open(f"https://www.google.com/search?q={app_or_site}")
                        return f"Searching for {app_or_site}"
                except:
                    return f"I couldn't open {app_or_site}"
        elif "close" in command:
            app = command.replace("close", "").strip()
            return f"Closed {app}" if close_application(app) else f"I couldn't find {app} to close"
        elif "search" in command or "look up" in command:
            query = command.replace("search", "").replace("look up", "").strip()
            if query:
                result = duckduckgo_search(query)
                if result:
                    return result[:200] + "..." if len(result) > 200 else result
                else:
                    webbrowser.open(f"https://www.google.com/search?q={query}")
                    return f"I couldn't find a quick answer, so I opened a search for {query}"
            return "What would you like me to search for?"
        elif "volume" in command:
            try:
                if "set volume" in command or "volume to" in command:
                    words = command.split()
                    for word in words:
                        if word.isdigit():
                            level = int(word)
                            if 0 <= level <= 100:
                                return f"Volume set to {level}%" if set_volume(
                                    level) else "I couldn't change the volume"
                            return "Volume must be between 0 and 100"
                elif "increase volume" in command or "volume up" in command:
                    return "Volume increased" if set_volume(75) else "I couldn't increase the volume"
                elif "decrease volume" in command or "volume down" in command:
                    return "Volume decreased" if set_volume(25) else "I couldn't decrease the volume"
                return "Please specify a volume level between 0 and 100"
            except:
                return "I couldn't change the volume"
        elif "brightness" in command:
            try:
                if "set brightness" in command or "brightness to" in command:
                    words = command.split()
                    for word in words:
                        if word.isdigit():
                            level = int(word)
                            if 0 <= level <= 100:
                                return f"Brightness set to {level}%" if set_brightness(
                                    level) else "I couldn't change the brightness"
                            return "Brightness must be between 0 and 100"
                elif "increase brightness" in command or "brightness up" in command:
                    return "Brightness increased" if set_brightness(80) else "I couldn't increase the brightness"
                elif "decrease brightness" in command or "brightness down" in command:
                    return "Brightness decreased" if set_brightness(30) else "I couldn't decrease the brightness"
                return "Please specify a brightness level between 0 and 100"
            except:
                return "I couldn't change the brightness"
        elif "weather" in command:
            location = command.split(" in ")[-1].strip() if " in " in command else "current location"
            webbrowser.open(f"https://www.google.com/search?q=weather+{location}")
            return f"Opening weather information for {location}"
        else:
            return ask_gemini(command)
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}"