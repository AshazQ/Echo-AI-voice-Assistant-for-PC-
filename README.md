# Echo - Personal Desktop Voice Assistant  

Echo is a **Python-based desktop voice assistant** built with **PyQt6** for the GUI.  
It listens to your commands, responds with natural speech, and automates system tasks like opening apps, searching the web, playing music, and setting reminders.  

---

# Features  
- **Voice Recognition** – Speech-to-text using `SpeechRecognition` (Google API)  
- **Text-to-Speech** – Natural voice responses (Microsoft Edge TTS / pyttsx3)  
- **Chat feature** - Can chat with the assistant.
- **Web & Media**  
  - Wikipedia search  
  - DuckDuckGo/Google queries  
  - Play YouTube songs/videos  
- **System Control**  
  - Open / close applications  
  - Control volume & brightness  
  - Show current time/date/day  
- **Productivity**  
  - Set reminders with toast + voice alert  
  - Maintains short-term context memory  
- **Modern GUI (PyQt6)**  
  - Window with mic, stop, and settings  
  - Speech feedback & draggable widget  
  - Interrupts itself when user talks over it
  - Shows the chat  

---

## Tech Stack  

- **Language:** Python 3.9+  
- **GUI:** PyQt6  
- **Libraries:**  
  - `speechrecognition` – for voice input  
  - `pyttsx3` or Edge TTS – for voice output  
  - `wikipedia`, `duckduckgo-search` – for information retrieval  
  - `pycaw`, `screen-brightness-control` – for system utilities  

---

## Installation  

1. Clone the repo:  
   ```bash
   git clone https://github.com/AshazQ/Echo-Voice-Assistant.git
   cd Echo-Voice-Assistant
