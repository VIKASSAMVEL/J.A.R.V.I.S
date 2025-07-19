import customtkinter as ctk
import tkinter as tk
import sys, ctypes
from PIL import Image, ImageDraw
import speech_recognition as sr
import logging
import json
import pyttsx3
import threading
import datetime
import psutil
import torch
import requests
import os
import subprocess
import webbrowser
import pyautogui
import keyboard
import screen_brightness_control as sbc
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM, TextGenerationPipeline
from typing import Optional
import random
import time
import config  # Import the configuration file

# --- LOGGING SETUP ---
def setup_logging():
    """Configures the logging for the application."""
    log_file = "jarvis.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s (%(filename)s:%(lineno)d)",
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger("httpx").setLevel(logging.WARNING) # Suppress overly verbose library logs

# --- CORE FUNCTIONS ---
def wish_me(app_instance):
    """Greets the user based on the time of day."""
    hour = datetime.datetime.now().hour
    greeting = ""
    if 0 <= hour < 12:
        greeting = f"Good morning, {config.USER_NAME}."
    elif 12 <= hour < 18:
        greeting = f"Good afternoon, {config.USER_NAME}."
    else:
        greeting = f"Good evening, {config.USER_NAME}."
    
    welcome_message = f"{greeting} I am {config.ASSISTANT_NAME}, your personal AI assistant. How may I help you today?"
    app_instance.add_to_chat_log(f"{config.ASSISTANT_NAME}: {welcome_message}", "Assistant")
    app_instance._speak(welcome_message)
# --- GUI CLASS ---

class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Sci-Fi Theme Colors ---
        self.BG_COLOR = "#081018"
        self.FRAME_COLOR = "#101820"
        self.PRIMARY_ACCENT = "#00FFFF"  # Cyan
        self.SECONDARY_ACCENT = "#415A77"
        self.TEXT_COLOR = "#E0E1DD"
        self.USER_COLOR = "#5DADE2"
        self.ASSISTANT_COLOR = self.PRIMARY_ACCENT
        self.ERROR_COLOR = "#FF474C"
        self.STATUS_COLOR = "#FFD700"

        # --- Window Setup ---
        self.title(f"{config.ASSISTANT_NAME} - AI Assistant")
        self.geometry("1000x600")
        self.resizable(False, False)
        self.configure(fg_color=self.BG_COLOR)

        # --- State Variables ---
        self.tts_engine = None
        self.tts_lock = threading.Lock()  # Add a lock for TTS
        self.chatbot: Optional[TextGenerationPipeline] = None
        self.chat_history: list[str] = []
        self.weather_data = "Weather: Initializing..."
        self.news_data = "News: Initializing..."
        self.is_initialized = False # Flag to prevent re-running initial tasks
        self.is_voice_mode = True # Start in voice-first mode

        # --- Voice Recognition State ---
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.microphone = sr.Microphone()
        self.stop_listening = None # Will hold the callback to stop listening

        # --- Custom Commands ---
        self.custom_commands_file = "custom_commands.json"
        self.custom_commands = {}
        self._load_custom_commands()

        # --- Command Dispatcher ---
        # This map links keywords to their handler methods.
        # Using tuples for keys allows multiple keywords to trigger the same handler.
        # More specific commands (like 'learn command') should come first.
        self.command_map = {
            ('learn command', 'create command'): self._handle_learn_command,
            ('list commands', 'what can you do', 'show commands'): self._handle_list_commands,
            ('date',): self._handle_date,
            ('search for',): self._handle_search,
            ('open youtube',): self._handle_open_youtube,
            ('open google',): self._handle_open_google,
            ('open notepad',): self._handle_open_notepad,
            ('close notepad',): self._handle_close_notepad,
            ('open command prompt', 'open cmd'): self._handle_open_cmd,
            ('open file explorer',): self._handle_open_explorer,
            ('shutdown',): self._handle_shutdown,
            ('restart',): self._handle_restart,
            ('sleep',): self._handle_sleep,
            ('brightness',): self._handle_brightness,
            ('weather',): self._handle_weather,
            ('play music',): self._handle_play_music,
            ('type',): self._handle_type,
            ('screenshot', 'take a screenshot'): self._handle_screenshot,
            ('news', 'headlines'): self._handle_news,
            ('launch',): self._handle_launch_app,
            ('move mouse to',): self._handle_mouse_move,
            ('left click', 'right click', 'double click'): self._handle_mouse_click,
            ('press key',): self._handle_key_press,
            ('time',): self._handle_time,
            ('hello', 'hey'): self._handle_greeting, # General greetings last
        }

        # --- Theme and Fonts ---
        ctk.set_appearance_mode("dark") # Enforce dark mode for the sci-fi theme
        try:
            self.font = (config.FONT_FAMILY, 14)
            self.font_bold = (config.FONT_FAMILY, 14, "bold")
        except tk.TclError:
            self.font = (config.FALLBACK_FONT, 12)
            self.font_bold = (config.FALLBACK_FONT, 12, "bold")
            logging.warning(f"Font '{config.FONT_FAMILY}' not found, using fallback '{config.FALLBACK_FONT}'.")

        # --- Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Status & Controls) ---
        self.left_frame = ctk.CTkFrame(self, width=250, corner_radius=10, fg_color=self.FRAME_COLOR)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # --- Right Frame (Chat & Input) ---
        self.right_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=self.FRAME_COLOR)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        self.create_left_widgets()
        self.create_right_widgets()

        # --- Start background tasks and initialization ---
        self.update_status_labels()
        self.start_initialization()

        # Bind key presses on the main window to switch to text mode
        self.bind("<KeyPress>", self._on_key_press_anywhere)

    def initialize_tts(self):
        """Initializes the TTS engine."""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', config.TTS_RATE)
            self.tts_engine.setProperty('volume', config.TTS_VOLUME)
            voices = self.tts_engine.getProperty('voices')
            if 0 <= config.TTS_VOICE_ID < len(voices):
                self.tts_engine.setProperty('voice', voices[config.TTS_VOICE_ID].id)
            else:
                logging.warning(f"TTS Voice ID {config.TTS_VOICE_ID} is invalid. Falling back to default voice.")
            logging.info("TTS Engine initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize TTS engine: {e}", exc_info=True)
            self.add_to_chat_log(f"TTS Error: {e}", "Error")

    def initialize_chatbot(self):
        """Initializes the chatbot pipeline, using GPU if available."""
        device = -1 # Default to CPU
        device_name = "CPU"
        try:
            if torch.cuda.is_available():
                device = 0 # Use the first GPU
                device_name = torch.cuda.get_device_name(device)
                logging.info(f"CUDA GPU detected: {device_name}. Initializing chatbot on GPU.")
            else:
                logging.info("No CUDA GPU detected. Initializing chatbot on CPU.")

            tokenizer = AutoTokenizer.from_pretrained(config.CHATBOT_MODEL)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            model_kwargs = {'weights_only': True}
            model = AutoModelForCausalLM.from_pretrained(config.CHATBOT_MODEL, **model_kwargs)
            self.chatbot = TextGenerationPipeline(model=model, tokenizer=tokenizer, device=device)
            logging.info(f"Chatbot initialized successfully on {device_name}.")
        except Exception as e:
            logging.critical(f"FATAL: Failed to initialize chatbot: {e}", exc_info=True)
            self.add_to_chat_log(f"Chatbot Error: {e}", "Error")

    def _calibrate_microphone(self):
        """Adjusts the recognizer sensitivity to ambient noise."""
        try:
            with self.microphone as source:
                logging.info("Calibrating microphone for ambient noise... Please wait.")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logging.info("Microphone calibrated.")
        except Exception as e:
            logging.error(f"Could not calibrate microphone: {e}", exc_info=True)

    def get_chatbot_response(self, user_input: str) -> str:
        """Gets a response from the chatbot, managing conversation history."""
        if not self.chatbot or not self.chatbot.tokenizer:
            return "The chatbot is not available at the moment."

        # Append new user input to the history
        self.chat_history.append(user_input)

        # Construct the prompt string from the history, separated by the EOS token
        eos_token = self.chatbot.tokenizer.eos_token
        prompt = eos_token.join(self.chat_history) + eos_token

        # Call the text-generation pipeline
        try:
            outputs = self.chatbot(
                prompt,
                max_new_tokens=70,  # Max words in the new response
                pad_token_id=self.chatbot.tokenizer.eos_token_id, # Crucial for DialoGPT
                top_k=50,           # Select from top 50 most likely words
                top_p=0.95,         # Use nucleus sampling
                do_sample=True      # Enable sampling for more creative responses
            )
        except Exception as e:
            logging.error(f"Chatbot generation error: {e}", exc_info=True)
            return "Sorry, I couldn't generate a response."
        
        # Safely extract the response text from the pipeline's output.
        response = ""
        if isinstance(outputs, list) and outputs and isinstance(outputs[0], dict):
            full_response_text = outputs[0].get('generated_text', '')
            response = full_response_text.replace(prompt, '').strip()

        # Add the bot's response to the history and truncate if necessary
        if response:
            self.chat_history.append(response)
            if len(self.chat_history) > config.MAX_CHAT_HISTORY * 2:
                self.chat_history = self.chat_history[-(config.MAX_CHAT_HISTORY * 2):]

        return response or "I'm not sure how to respond to that."

    def fetch_and_update_info(self):
        """Fetches weather and news data in the background and schedules the next update."""
        # --- Fetch Weather ---
        if not config.OPENWEATHER_API_KEY or config.OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY":
            self.weather_data = "Weather: API Key Missing"
        else:
            try:
                city = config.USER_CITY
                url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={config.OPENWEATHER_API_KEY}&units=metric"
                res = requests.get(url, timeout=10).json()
                if res.get("cod") == 200:
                    temp = res["main"]["temp"]
                    desc = res["weather"][0]["description"]
                    self.weather_data = f"Weather: {temp}°C, {desc.capitalize()}"
                else:
                    self.weather_data = "Weather: City Not Found"
            except Exception as e:
                logging.error(f"Error fetching weather for UI: {e}")
                self.weather_data = "Weather: Connection Error"

        # --- Fetch News ---
        if not config.NEWS_API_KEY or config.NEWS_API_KEY == "YOUR_NEWSAPI_KEY":
            self.news_data = "News: API Key Missing"
        else:
            try:
                url = f"https://newsapi.org/v2/top-headlines?country={config.NEWS_COUNTRY_CODE}&apiKey={config.NEWS_API_KEY}"
                response = requests.get(url, timeout=10).json()
                if response.get("status") == "ok" and response.get("articles"):
                    first_headline = response["articles"][0]['title']
                    self.news_data = f"News: {first_headline}"
                else:
                    self.news_data = "News: Not available"
            except Exception as e:
                logging.error(f"Error fetching news for UI: {e}")
                self.news_data = "News: Connection Error"

        # Schedule the GUI update and the next fetch (every 15 minutes)
        self.after(0, self._update_info_display)
        self.after(15 * 60 * 1000, lambda: threading.Thread(target=self.fetch_and_update_info, daemon=True).start())

    # --- Custom Command Management ---
    def _load_custom_commands(self):
        """Loads custom commands from a JSON file."""
        try:
            if os.path.exists(self.custom_commands_file):
                with open(self.custom_commands_file, 'r') as f:
                    self.custom_commands = json.load(f)
                    logging.info(f"Loaded {len(self.custom_commands)} custom commands.")
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading custom commands from {self.custom_commands_file}: {e}")
            self.custom_commands = {} # Reset to empty on error

    def _save_custom_commands(self):
        """Saves the current custom commands to a JSON file."""
        try:
            with open(self.custom_commands_file, 'w') as f:
                json.dump(self.custom_commands, f, indent=4)
                logging.info(f"Custom commands saved to {self.custom_commands_file}")
        except IOError as e:
            logging.error(f"Error saving custom commands to {self.custom_commands_file}: {e}")

    def _execute_custom_command(self, command_data):
        """Executes a dynamically learned custom command."""
        action_type = command_data.get("type")
        target = command_data.get("target")

        if action_type == "open":
            if os.path.exists(target):
                os.startfile(target)
                return f"Opening {os.path.basename(target)}."
            else:
                return f"Sorry, I could not find the path: {target}."
        elif action_type == "website":
            webbrowser.open(target)
            return f"Opening the website: {target}."
        elif action_type == "type":
            self._speak(f"Typing: {target}")
            pyautogui.write(target, interval=0.1)
            return None # Avoid double speaking
        return f"Unknown custom command type: {action_type}"

    # --- Speaking Method with UI Indicator ---
    def _speak(self, text: Optional[str]):
        """Converts text to speech, thread-safe, and updates GUI indicator."""
        if not text or not self.tts_engine:
            self.after(0, self._hide_speaking_indicator)
            return
        try:
            # Show indicator (scheduled from any thread)
            self.after(0, self._show_speaking_indicator)
            with self.tts_lock:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
        except Exception as e:
            logging.error(f"Error in _speak method: {e}", exc_info=True)
        finally:
            # Always hide indicator after a short delay to ensure UI updates
            self.after(200, self._hide_speaking_indicator)

    # --- Command Processing ---
    def process_command(self, query):
        """Processes the user's command by dispatching to the appropriate handler."""
        # First, check for an exact match with custom learned commands
        if query in self.custom_commands:
            try:
                command_data = self.custom_commands[query]
                response = self._execute_custom_command(command_data)
                self._speak_and_log(response)
                return # Command handled
            except Exception as e:
                error_message = f"An error occurred while running your custom command: {e}"
                logging.error(error_message, exc_info=True)
                self.add_to_chat_log(error_message, "Error")
                return

        # Then, check for built-in commands using keyword matching
        for keywords, handler in self.command_map.items():
            for keyword in keywords:
                if keyword in query:
                    try:
                        response = handler(query)
                        self._speak_and_log(response)
                        return # Command handled
                    except Exception as e:
                        error_message = f"An error occurred while handling the command: {e}"
                        logging.error(error_message, exc_info=True)
                        self.add_to_chat_log(error_message, "Error")
                        return

        # --- Fallback to Chatbot ---
        if query and query != "none":
            response = self.get_chatbot_response(query)
            self._speak_and_log(response)  # Always speak chatbot responses

    # --- Command Handlers ---
    def _speak_and_log(self, response_text):
        """Logs the assistant's response and speaks it, if not empty."""
        if response_text:
            self.add_to_chat_log(f"{config.ASSISTANT_NAME}: {response_text}", "Assistant")
            self._speak(response_text)

    def _handle_greeting(self, query):
        return f"Hello {config.USER_NAME}, how can I assist you?"

    def _handle_time(self, query):
        return datetime.datetime.now().strftime("%I:%M %p")

    def _handle_date(self, query):
        return datetime.datetime.now().strftime("%B %d, %Y")

    def _handle_search(self, query):
        search_term = query.replace('search for', '').strip()
        url = f"https://www.google.com/search?q={search_term}"
        webbrowser.open(url)
        return f"Searching for {search_term} on Google."

    def _handle_open_youtube(self, query):
        webbrowser.open("https://youtube.com")
        return "Opening YouTube."

    def _handle_open_google(self, query):
        webbrowser.open("https://google.com")
        return "Opening Google."

    def _handle_open_notepad(self, query):
        try:
            subprocess.Popen(['notepad.exe'])
            return "Opening Notepad."
        except FileNotFoundError:
            return "Notepad not found. Please check your system."

    def _handle_close_notepad(self, query):
        subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True, text=True)
        return "Closing Notepad."

    def _handle_open_cmd(self, query):
        subprocess.Popen(['cmd.exe'])
        return "Opening Command Prompt."

    def _handle_open_explorer(self, query):
        subprocess.Popen(['explorer.exe'])
        return "Opening File Explorer."

    def _handle_shutdown(self, query):
        response = "Shutting down the system in 5 seconds. Please save your work."
        self._speak(response)
        subprocess.run(["shutdown", "/s", "/t", "5"])
        return None # Prevent the main loop from speaking

    def _handle_restart(self, query):
        response = "Restarting the system in 5 seconds. Please save your work."
        self._speak(response)
        subprocess.run(["shutdown", "/r", "/t", "5"])
        return None # Prevent the main loop from speaking

    def _handle_sleep(self, query):
        response = "Putting the system to sleep."
        self._speak(response)
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return None # Prevent the main loop from speaking

    def _handle_brightness(self, query):
        try:
            level = int(''.join(filter(str.isdigit, query)))
            if 0 <= level <= 100:
                sbc.set_brightness(level)
                return f"Brightness set to {level}%."
            else:
                return "Brightness level must be between 0 and 100."
        except (ValueError, IndexError):
            current_brightness = sbc.get_brightness()
            if isinstance(current_brightness, list):
                brightness_value = current_brightness[0] if current_brightness else "N/A"
            else:
                brightness_value = current_brightness
            return f"Current brightness is at {brightness_value}%."
        except Exception as e:
            return f"Sorry, I can't control brightness on this device. Error: {e}"

    def _handle_weather(self, query):
        if config.OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY" or not config.OPENWEATHER_API_KEY:
            return "Weather API key is not configured. Please set it in the config file."
        try:
            city = config.USER_CITY # Default city from config
            if "in" in query:
                city = query.split("in")[-1].strip()
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={config.OPENWEATHER_API_KEY}&units=metric"
            res = requests.get(url, timeout=10).json()
            if res.get("cod") == 200:
                temp = res["main"]["temp"]
                desc = res["weather"][0]["description"]
                return f"The weather in {city} is {temp}°C with {desc}."
            else:
                return f"Sorry, I couldn't find the weather for {city}."
        except Exception as e:
            return f"Error fetching weather data: {e}"

    def _handle_play_music(self, query):
        try:
            if os.path.exists(config.MUSIC_DIR):
                songs = [s for s in os.listdir(config.MUSIC_DIR) if s.endswith(('.mp3', '.wav'))]
                if songs:
                    random_song = os.path.join(config.MUSIC_DIR, random.choice(songs))
                    os.startfile(random_song)
                    return "Playing a random song from your library."
                else:
                    return "No music files found in the specified directory."
            else:
                return "Music directory not found. Please configure it in the config file."
        except Exception as e:
            return f"Could not play music. Error: {e}"

    def _handle_type(self, query):
        text_to_type = query.replace('type', '').strip()
        response = f"Typing: {text_to_type}"
        self._speak(response)
        pyautogui.write(text_to_type, interval=0.1)
        return None # Avoid double speaking

    def _handle_screenshot(self, query):
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            # Save to the user's desktop
            file_path = os.path.join(os.path.expanduser("~"), "Desktop", f"screenshot_{timestamp}.png")
            pyautogui.screenshot(file_path)
            return f"Screenshot saved to your desktop as screenshot_{timestamp}.png"
        except Exception as e:
            return f"Sorry, I couldn't take a screenshot. Error: {e}"

    def _handle_news(self, query):
        if not config.NEWS_API_KEY or config.NEWS_API_KEY == "YOUR_NEWSAPI_KEY":
            return "News API key is not configured. Please get one from newsapi.org and add it to your config file."
        try:
            url = f"https://newsapi.org/v2/top-headlines?country={config.NEWS_COUNTRY_CODE}&apiKey={config.NEWS_API_KEY}"
            response = requests.get(url, timeout=10).json()
            if response.get("status") == "ok":
                articles = response.get("articles", [])
                if not articles:
                    return "I couldn't find any news headlines at the moment."
                headlines = [f"• {article['title']}" for article in articles[:3]] # Get top 3
                return "Here are the top headlines:\n" + "\n".join(headlines)
            else:
                return f"Sorry, there was an issue fetching the news: {response.get('message', 'Unknown error')}"
        except Exception as e:
            return f"An error occurred while fetching news: {e}"

    def _handle_launch_app(self, query):
        """Launches an application based on the configuration."""
        # e.g., "launch spotify" -> "spotify"
        app_name = query.replace('launch', '').strip().lower()
        if not app_name:
            return "Which application would you like to launch?"

        app_path = config.APPLICATION_PATHS.get(app_name)

        if not app_path:
            return f"Sorry, I don't have the path for {app_name}. You can add it to the config file."

        # Special handling for Microsoft Store apps (WindowsApps)
        if "windowsapps" in app_path.lower():
            # Try to launch using the URI protocol if known
            if app_name == "spotify":
                try:
                    os.startfile("spotify:")
                    return "Launching Spotify."
                except Exception as e:
                    return f"Failed to launch Spotify: {e}"
            # Add more app_name checks here if needed
            return f"Cannot launch {app_name} directly due to Windows Store app restrictions."

        if os.path.exists(app_path):
            subprocess.Popen([app_path])
            return f"Launching {app_name}."
        else:
            return f"The configured path for {app_name} does not exist. Please check the config file."

    def _handle_mouse_move(self, query):
        """Moves the mouse to specified X, Y coordinates."""
        try:
            coords_str = query.replace('move mouse to', '').strip()
            x_str, y_str = coords_str.split()
            x, y = int(x_str), int(y_str)
            pyautogui.moveTo(x, y, duration=0.5)
            return f"Moving mouse to {x}, {y}."
        except ValueError:
            return "Invalid coordinates. Please say something like 'move mouse to 800 600'."
        except Exception as e:
            return f"Could not move mouse. Error: {e}"

    def _handle_mouse_click(self, query):
        """Performs a mouse click."""
        if 'left click' in query:
            pyautogui.leftClick()
            return "Left click."
        elif 'right click' in query:
            pyautogui.rightClick()
            return "Right click."
        elif 'double click' in query:
            pyautogui.doubleClick()
            return "Double click."
        return None # Should not happen if mapped correctly

    def _handle_key_press(self, query):
        """Presses a specified keyboard key."""
        key_to_press = query.replace('press key', '').strip().lower()
        if not key_to_press:
            return "Which key should I press?"
        pyautogui.press(key_to_press)
        return f"Pressed the {key_to_press} key."

    def _handle_list_commands(self, query):
        """Provides a summary of available commands."""
        response_parts = [
            "I can perform a variety of tasks. Here's a summary of what I can do:"
        ]

        # Built-in capabilities summary
        built_in_summary = [
            "• Information: Get the time, date, weather, and latest news headlines.",
            "• Web: Search Google or open YouTube.",
            "• System Control: Shutdown, restart, sleep, or adjust screen brightness.",
            "• Applications: Open Notepad, or launch custom apps like Chrome if configured.",
            "• Automation: Take a screenshot, type text for me, move the mouse, or press keyboard keys.",
            "• Media: Play a random song from your music library."
        ]
        response_parts.extend(built_in_summary)

        # Custom commands summary
        if self.custom_commands:
            custom_command_list = list(self.custom_commands.keys())
            examples = ", ".join(f"'{c}'" for c in custom_command_list[:3]) # Show up to 3 examples
            response_parts.append(f"• Custom Commands: I can run the commands you've taught me, such as {examples}.")

        response_parts.append("\nYou can also teach me new tasks by saying 'learn command', or just chat with me about anything else.")
        return "\n".join(response_parts)

    def _handle_learn_command(self, query):
        """Initiates the process of learning a new command via GUI dialogs."""
        self.after(100, self._start_learning_flow)
        return "Okay, opening the command learning interface. Please use the dialog boxes that appear."

    def _start_learning_flow(self):
        """Guides the user through creating a new command using a series of dialogs."""
        try:
            # Step 1: Get command phrase
            dialog1 = ctk.CTkInputDialog(text="What is the new command phrase you want to teach me?\n(e.g., 'open my project')", title="Learn Command: Step 1 of 3")
            phrase_input = dialog1.get_input()
            if not phrase_input:
                self.add_to_chat_log("Learning cancelled by user.", "Status")
                return
            phrase = phrase_input.strip().lower() # Standardize to lowercase

            # Step 2: Get action type
            dialog2 = ctk.CTkInputDialog(text="What should this command do?\nType 'open', 'website', or 'type'.", title="Learn Command: Step 2 of 3")
            action_type_input = dialog2.get_input()
            if not action_type_input:
                self.add_to_chat_log("Learning cancelled by user.", "Status")
                return

            action_type = action_type_input.lower().strip()
            if action_type not in ['open', 'website', 'type']:
                self.add_to_chat_log(f"Invalid action type '{action_type}'. Learning cancelled.", "Error")
                self._speak(f"Invalid action type. Learning cancelled.")
                return

            # Step 3: Get action target
            prompt_text = ""
            if action_type == 'open':
                prompt_text = "What is the full path to the file or folder to open?"
            elif action_type == 'website':
                prompt_text = "What is the full URL of the website to open?\n(e.g., https://www.github.com)"
            elif action_type == 'type':
                prompt_text = "What is the exact text you want me to type?"

            dialog3 = ctk.CTkInputDialog(text=prompt_text, title="Learn Command: Step 3 of 3")
            target = dialog3.get_input()
            if not target:
                self.add_to_chat_log("Learning cancelled by user.", "Status")
                return

            # Step 4: Save the command
            self.custom_commands[phrase] = {"type": action_type, "target": target.strip()}
            self._save_custom_commands()

            success_message = f"New command learned! Say '{phrase}' to trigger it."
            self.add_to_chat_log(success_message, "Status")
            self._speak(success_message)

        except Exception as e:
            error_message = f"An error occurred during the learning process: {e}"
            logging.error(error_message, exc_info=True)
            self.add_to_chat_log(error_message, "Error")

    def create_left_widgets(self):
        """Creates widgets for the left status frame."""
        # --- Title ---
        title_label = ctk.CTkLabel(self.left_frame, text=config.ASSISTANT_NAME.upper(), font=(self.font[0], 24, "bold"), text_color=self.PRIMARY_ACCENT)
        title_label.pack(pady=20)

        # --- Status Labels ---
        status_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        status_frame.pack(pady=10, padx=20, fill="x")

        self.time_label = ctk.CTkLabel(status_frame, text="Time: --:--:--", font=self.font)
        self.time_label.pack(anchor="w")

        self.date_label = ctk.CTkLabel(status_frame, text="Date: --/--/----", font=self.font)
        self.date_label.pack(anchor="w", pady=(5,0))

        self.cpu_label = ctk.CTkLabel(status_frame, text="CPU: --%", font=self.font)
        self.cpu_label.pack(anchor="w", pady=(5,0))

        self.battery_label = ctk.CTkLabel(status_frame, text="Battery: --%", font=self.font)
        self.battery_label.pack(anchor="w", pady=(5,0))

        # Add a separator for visual clarity
        ctk.CTkFrame(status_frame, height=2, fg_color=self.PRIMARY_ACCENT).pack(fill="x", pady=10)

        self.weather_label = ctk.CTkLabel(status_frame, text="Weather: --", font=self.font, justify=tk.LEFT, wraplength=180)
        self.weather_label.pack(anchor="w", pady=(5,0))

        self.news_label = ctk.CTkLabel(status_frame, text="News: --", font=self.font, justify=tk.LEFT, wraplength=180)
        self.news_label.pack(anchor="w", pady=(5,0))

        # Add a separator for the speaking indicator
        ctk.CTkFrame(status_frame, height=2, fg_color=self.SECONDARY_ACCENT).pack(fill="x", pady=(10, 5))

        # --- Speaking Indicator ---
        self.speaking_indicator_label = ctk.CTkLabel(status_frame, text="... SPEAKING ...", font=self.font_bold, text_color=self.PRIMARY_ACCENT)
        # This label is initially hidden and will be shown/hidden by pack() and pack_forget()

    def _show_speaking_indicator(self):
        self.speaking_indicator_label.pack(anchor="w", pady=(5,0))

    def _hide_speaking_indicator(self):
        self.speaking_indicator_label.pack_forget()

    def load_mic_icons(self):
        """Loads different mic icons for each state (idle, listening, recognizing, processing)."""
        from PIL import ImageEnhance
        base_icon_path = "mic_icon.png"
        if not os.path.exists(base_icon_path):
            # Create a default icon if missing (already handled in create_right_widgets)
            return None, None, None, None
        base_icon = Image.open(base_icon_path).convert("RGBA")
        # Idle: Cyan (default)
        mic_idle = ctk.CTkImage(light_image=base_icon, dark_image=base_icon, size=(24, 24))
        # Listening: Red overlay
        mic_listening = ctk.CTkImage(light_image=self._tint_image(base_icon, self.ERROR_COLOR), dark_image=self._tint_image(base_icon, self.ERROR_COLOR), size=(24, 24))
        # Recognizing: Yellow overlay
        mic_recognizing = ctk.CTkImage(light_image=self._tint_image(base_icon, self.STATUS_COLOR), dark_image=self._tint_image(base_icon, self.STATUS_COLOR), size=(24, 24))
        # Processing: Blue overlay
        mic_processing = ctk.CTkImage(light_image=self._tint_image(base_icon, self.SECONDARY_ACCENT), dark_image=self._tint_image(base_icon, self.SECONDARY_ACCENT), size=(24, 24))
        return mic_idle, mic_listening, mic_recognizing, mic_processing

    def _tint_image(self, image, color):
        """Tints a PIL image with the given color (hex)."""
        color = color.lstrip('#')
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        rgba = (rgb[0], rgb[1], rgb[2], 120)  # Explicit 4-tuple for RGBA
        overlay = Image.new('RGBA', image.size, rgba)  # type: ignore
        return Image.alpha_composite(image, overlay)

    def set_mic_state(self, state):
        """Updates the mic icon and button color based on state. States: idle, listening, recognizing, processing."""
        if not hasattr(self, 'mic_icons'):
            return
        icon_idle, icon_listening, icon_recognizing, icon_processing = self.mic_icons
        if state == "idle":
            self.mic_button.configure(image=icon_idle, fg_color=self.PRIMARY_ACCENT)
        elif state == "listening":
            self.mic_button.configure(image=icon_listening, fg_color=self.ERROR_COLOR)
        elif state == "recognizing":
            self.mic_button.configure(image=icon_recognizing, fg_color=self.STATUS_COLOR)
        elif state == "processing":
            self.mic_button.configure(image=icon_processing, fg_color=self.SECONDARY_ACCENT)

    def create_right_widgets(self):
        """Creates widgets for the right chat frame."""
        # --- Chat Log ---
        self.chat_log = ctk.CTkTextbox(self.right_frame, state="disabled", corner_radius=10, font=self.font, wrap="word",
                                   fg_color=self.FRAME_COLOR, border_color=self.SECONDARY_ACCENT, border_width=1)
        self.chat_log.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.chat_log.tag_config("User", foreground=self.USER_COLOR)
        self.chat_log.tag_config("Assistant", foreground=self.ASSISTANT_COLOR)
        self.chat_log.tag_config("Error", foreground=self.ERROR_COLOR)
        self.chat_log.tag_config("Status", foreground=self.STATUS_COLOR)

        self.entry_field = ctk.CTkEntry(self.right_frame, placeholder_text=f"Type your command, {config.USER_NAME}...", font=self.font,
                                    fg_color=self.FRAME_COLOR, border_color=self.SECONDARY_ACCENT, border_width=1)
        self.entry_field.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="ew")
        self.entry_field.bind("<Return>", self.handle_text_input)

        # --- Microphone Button ---
        # For the best look, create a 24x24px transparent PNG icon named 'mic_icon.png'
        try:
            # Create a dummy icon file if it doesn't exist for demonstration
            if not os.path.exists("mic_icon.png"):
                img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))  # type: ignore
                draw = ImageDraw.Draw(img)
                # Simple mic shape using theme colors
                draw.rectangle(xy=[(24, 8), (40, 36)], fill=self.PRIMARY_ACCENT, outline=self.SECONDARY_ACCENT)
                draw.rectangle(xy=[(28, 4), (36, 8)], fill=self.PRIMARY_ACCENT, outline=self.SECONDARY_ACCENT)
                draw.line([(32, 36), (32, 48)], fill=self.SECONDARY_ACCENT, width=4)
                draw.rectangle(xy=[(20, 48), (44, 56)], fill=self.SECONDARY_ACCENT)
                img.save('mic_icon.png')

            mic_icon_path = "mic_icon.png"
            mic_icon = Image.open(mic_icon_path)
            mic_image = ctk.CTkImage(light_image=mic_icon, dark_image=mic_icon, size=(24, 24))
            self.mic_button = ctk.CTkButton(
                self.right_frame,
                image=mic_image,
                text="",
                width=40,
                height=40,
                corner_radius=20,
                fg_color=self.PRIMARY_ACCENT,
                hover_color="#00DDEE",
                command=self.handle_voice_input
            )
            # Load all mic icons for state changes
            self.mic_icons = self.load_mic_icons()
        except Exception as e:
            logging.warning(f"Could not create or load 'mic_icon.png' ({e}). Using text fallback for mic button.")
            # Fallback if icon is missing
            self.mic_button = ctk.CTkButton(
                self.right_frame,
                text="🎤",
                width=40,
                height=40,
                font=(self.font[0], 20),
                text_color=self.BG_COLOR,
                command=self.handle_voice_input
            )
            self.mic_icons = (None, None, None, None)
        self.mic_button.grid(row=1, column=1, padx=5, pady=10)

    def start_initialization(self):
        """Disables inputs and starts background service initialization and polling."""
        # Disable inputs until services are ready
        self.entry_field.configure(state="disabled", placeholder_text="Initializing...")
        self.mic_button.configure(state="disabled")

        # Start initialization in threads
        threading.Thread(target=self.initialize_tts, daemon=True).start()
        threading.Thread(target=self.initialize_chatbot, daemon=True).start()
        threading.Thread(target=self._calibrate_microphone, daemon=True).start()
        threading.Thread(target=self.fetch_and_update_info, daemon=True).start()

        # Start polling to check when services are ready
        self.check_initialization()

    def check_initialization(self):
        """Periodically checks if services are ready and enables UI."""
        if self.chatbot is not None and self.tts_engine is not None and not self.is_initialized:
            self.is_initialized = True # Set flag to true
            self.entry_field.configure(placeholder_text="Voice mode active. Start typing to switch.")
            self.mic_button.configure(state="normal")
            
            # Greet the user now that all systems are online
            threading.Thread(target=wish_me, args=(self,), daemon=True).start()
        else:
            self.after(200, self.check_initialization) # Check again in 200ms if not ready

    def _update_info_display(self):
        """Updates the weather and news labels in the GUI."""
        self.weather_label.configure(text=self.weather_data)
        self.news_label.configure(text=self.news_data)

    def update_status_labels(self):
        """Periodically updates the status labels on the left frame."""
        # Time and Date
        now = datetime.datetime.now()
        self.time_label.configure(text=f"Time: {now.strftime('%I:%M:%S %p')}")
        self.date_label.configure(text=f"Date: {now.strftime('%B %d, %Y')}")

        # CPU Usage
        cpu_usage = psutil.cpu_percent()
        self.cpu_label.configure(text=f"CPU: {cpu_usage:.1f}%")

        # Battery
        try:
            battery = psutil.sensors_battery()
            if battery:
                plugged = "(Charging)" if battery.power_plugged else "(Discharging)"
                self.battery_label.configure(text=f"Battery: {battery.percent}% {plugged}")
            else:
                self.battery_label.configure(text="Battery: N/A")
        except (AttributeError, NotImplementedError):
             self.battery_label.configure(text="Battery: N/A")

        # Schedule the next update
        self.after(1000, self.update_status_labels)

    def _update_chat_log_display(self, message, sender):
        """Internal method to safely update the chat log from the main GUI thread."""
        self.chat_log.configure(state="normal")
        # Add a newline before the new message if the box isn't empty
        if len(self.chat_log.get("1.0", "end-1c")) > 0:
            self.chat_log.insert("end", "\n\n")

        self.chat_log.insert("end", message, (sender,))
        self.chat_log.see("end") # Auto-scroll
        self.chat_log.configure(state="disabled")

    def add_to_chat_log(self, message, sender=""):
        """Adds a message to the chat log with appropriate styling."""
        # Schedule the GUI update to run in the main thread
        self.after(0, lambda: self._update_chat_log_display(message, sender))

    def handle_text_input(self, event=None):
        """Handles text input from the entry field."""
        self.is_voice_mode = False # Entering text means we are in text mode
        query = self.entry_field.get()
        if query:
            self.add_to_chat_log(f"{config.USER_NAME}: {query}", "User")
            self.entry_field.delete(0, "end")
            self.run_command(query)

    def _on_key_press_anywhere(self, event):
        """Switches to text mode when the user starts typing anywhere."""
        # Ignore control keys
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock"):
            return

        if self.is_voice_mode:
            self.is_voice_mode = False
            self.entry_field.configure(state="normal", placeholder_text=f"Type your command, {config.USER_NAME}...")
            self.entry_field.focus()
            # The key press event is consumed, so we manually insert the character
            if event.char and event.char.isprintable():
                self.entry_field.insert(tk.END, event.char)

    def _process_audio_callback(self, recognizer, audio):
        """Callback function for background listener. This runs in a separate thread."""
        logging.info("_process_audio_callback triggered.")
        if not self.is_listening:
            logging.info("_process_audio_callback: Not listening, returning early.")
            self.stop_listening = None
            return
        self.after(0, lambda: self.set_mic_state("recognizing"))
        self.after(0, lambda: self.entry_field.configure(placeholder_text="Recognizing..."))
        try:
            query = recognizer.recognize_google(audio, language='en-us')
            logging.info(f"Speech recognized: {query}")
            self.after(0, self.add_to_chat_log, f"{config.USER_NAME}: {query}", "User")
            self.after(0, lambda: self.set_mic_state("processing"))
            self.run_command(query.lower())
        except sr.UnknownValueError:
            logging.warning("Speech Recognition could not understand audio.")
            self.after(0, self.add_to_chat_log, "Could not understand audio. Please try again.", "Error")
            self.after(0, self.reset_ui_after_command)
        except sr.RequestError as e:
            error_msg = f"Could not request results; {e}"
            logging.error(error_msg)
            self.after(0, self.add_to_chat_log, error_msg, "Error")
            self._speak("I am having trouble connecting to the speech service.")
            self.after(0, self.reset_ui_after_command)
        except Exception as e:
            logging.error(f"Exception in _process_audio_callback: {e}", exc_info=True)
            self.after(0, self.add_to_chat_log, f"Speech recognition error: {e}", "Error")
            self.after(0, self.reset_ui_after_command)
        finally:
            self.is_listening = False
            self.stop_listening = None

    def handle_voice_input(self):
        """Toggles the microphone listening state, with lock to prevent double-acquisition and ensures proper reset for repeated use."""
        if not hasattr(self, 'microphone_lock'):
            self.microphone_lock = threading.Lock()
        if not hasattr(self, '_mic_pending'):
            self._mic_pending = False
        if self._mic_pending:
            return  # Prevent double-presses while pending
        if not self.microphone_lock.acquire(blocking=False):
            return
        try:
            if self.is_listening:
                # --- STOP LISTENING ---
                if self.stop_listening:
                    self.stop_listening(wait_for_stop=False)
                    self.stop_listening = None
                self.is_listening = False
                self.set_mic_state("idle")
                self.entry_field.configure(placeholder_text="Processing...")
                self._mic_pending = True
                def after_stop():
                    self._mic_pending = False
                    if self.microphone_lock.locked():
                        self.microphone_lock.release()
                self.after(500, after_stop)  # Wait longer to ensure mic is released
            else:
                # --- START LISTENING ---
                self.is_listening = True
                if self.stop_listening:
                    self.stop_listening(wait_for_stop=False)
                    self.stop_listening = None
                self.set_mic_state("listening")
                self.entry_field.configure(state="disabled", placeholder_text="Listening... Press mic to stop.")
                self.add_to_chat_log("Listening...", "Status")
                self._mic_pending = True
                def start_listener():
                    try:
                        logging.info("Calling listen_in_background to start speech recognition.")
                        self.stop_listening = self.recognizer.listen_in_background(self.microphone, self._process_audio_callback)
                        logging.info("listen_in_background started successfully.")
                    except Exception as e:
                        logging.error(f"Failed to start listen_in_background: {e}", exc_info=True)
                        self.add_to_chat_log(f"Microphone error: {e}", "Error")
                        self.is_listening = False
                        self.stop_listening = None
                        self.set_mic_state("idle")
                        self.entry_field.configure(state="normal", placeholder_text=f"Type your command, {config.USER_NAME}...")
                    finally:
                        self._mic_pending = False
                        if self.microphone_lock.locked():
                            self.microphone_lock.release()
                self.after(500, start_listener)  # Wait before starting listener
        except Exception:
            if self.microphone_lock.locked():
                self.microphone_lock.release()
            raise
        # Always release lock after starting or stopping
        if not self.is_listening:
            self.microphone_lock.release()
        else:
            # Release lock after a short delay to allow background listener to start
            self.after(500, self.microphone_lock.release)

    def run_command(self, query):
        """Runs the command processing in a separate thread to avoid freezing the GUI."""
        def command_thread():
            if query and query != "none":
                self.process_command(query)
            # After processing, reset the UI
            self.after(0, self.reset_ui_after_command)
        threading.Thread(target=command_thread, daemon=True).start()

    def reset_ui_after_command(self):
        """Resets UI elements to their default state after a command is processed."""
        if self.is_initialized:
            self.mic_button.configure(state="normal")
        self.entry_field.configure(state="normal", placeholder_text=f"Type your command, {config.USER_NAME}...")
        self.set_mic_state("idle")


# --- MAIN EXECUTION ---

if __name__ == "__main__":
    setup_logging()

    # --- Initial Checks ---
    if not config.OPENWEATHER_API_KEY or config.OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY":
        logging.warning("OpenWeatherMap API key is not set in config.py. Weather feature will be disabled.")

    if not os.path.isdir(config.MUSIC_DIR):
        logging.warning(f"Music directory '{config.MUSIC_DIR}' not found. 'play music' feature will be disabled.")
    
    if not config.NEWS_API_KEY or config.NEWS_API_KEY == "YOUR_NEWSAPI_KEY":
        logging.warning("NewsAPI key is not set in config.py. News feature will be disabled.")
    
    if not config.USER_CITY or config.USER_CITY == "YourCity":
        logging.info("User city is not set in config.py. Weather will default to a pre-set value if not specified in command.")

    if not config.APPLICATION_PATHS:
        logging.info("The APPLICATION_PATHS dictionary in config.py is empty. The 'launch' command will only work for default apps.")

    logging.info("="*50)
    logging.info("Starting J.A.R.V.I.S. Application")
    logging.info(f"Assistant Name: {config.ASSISTANT_NAME}")
    logging.info(f"User Name: {config.USER_NAME}")
    logging.info("="*50)

    # Create and run the application
    app = JarvisApp()
    try:
        app.mainloop()
    except Exception as e:
        logging.critical("A fatal error occurred in the main application loop.", exc_info=True)
    finally:
        logging.info("="*50)
        logging.info("J.A.R.V.I.S. application shut down.")
        logging.info("="*50)
