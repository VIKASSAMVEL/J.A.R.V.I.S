# Configuration file for Jarvis

# --- API Keys and Paths ---
OPENWEATHER_API_KEY = "5fd03eb1df84e177df96229a5eabe09e"  # Get a free API key from https://openweathermap.org/
NEWS_API_KEY = "ef3e436cec7a40e98089db869c0cae55"  # Get a free API key from https://newsapi.org/
MUSIC_DIR = r"C:\\Users\\vikas\\Music"  # Path to your music library
USER_CITY = "Chennai"  # Default city for weather
NEWS_COUNTRY_CODE = "in"  # Country code for news headlines

# --- Assistant and User Names ---
ASSISTANT_NAME = "Jarvis"
USER_NAME = "Sir"

# --- Appearance ---
FONT_FAMILY = "Orbitron"  # Install this font for the best look
FALLBACK_FONT = "sans-serif"

# --- AI Model ---
CHATBOT_MODEL = "microsoft/DialoGPT-medium"
MAX_CHAT_HISTORY = 5

# --- TTS (Text-to-Speech) Settings ---
TTS_RATE = 150  # Words per minute
TTS_VOLUME = 1.0  # Volume (0.0 to 1.0)
TTS_VOICE_ID = 0  # Index of the voice to use

# --- Application Paths for 'launch' command ---
APPLICATION_PATHS = {
    'chrome': r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'notepad': r'C:\\Windows\\System32\\notepad.exe',
    'spotify': r'C:\\Program Files\\WindowsApps\\SpotifyAB.SpotifyMusic_1.266.447.0_x64__zpdnekdrzrea0\\Spotify.exe',
}
