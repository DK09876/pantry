from contextlib import contextmanager
import os
import sys
from pathlib import Path
import time
from google import genai
from google.genai.errors import APIError
from gtts import gTTS
from model_select import pick_model
import speech_recognition as sr


@contextmanager
def suppress_c_stderr():
  """Redirects C-level stderr output to suppress ALSA/JACK sound driver warnings."""
  try:
    null_fd = os.open(os.devnull, os.O_RDWR)
    save_fd = os.dup(2)
    os.dup2(null_fd, 2)
    yield
  finally:
    os.dup2(save_fd, 2)
    os.close(null_fd)
    os.close(save_fd)


from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

# Initialize Gemini Client
client = genai.Client()
MODEL = None


def speak(text):
  """Plays TTS via mpg123 to avoid ALSA conflicts with the microphone."""
  if not text.strip():
    return

  print(f"\nAI: {text}")
  file_path = "/tmp/response.mp3"

  # Pre-pad text slightly to prevent first-syllable clipping on hardware wake
  tts = gTTS(text=f". {text}", lang="en")
  tts.save(file_path)

  # Play via command line player; cleanly releases audio device when finished
  os.system(f"mpg123 -q {file_path}")

  if os.path.exists(file_path):
    os.remove(file_path)


def listen_for_audio(recognizer, source, phrase_limit=None):
  """Captures audio from microphone with improved noise filtering."""
  try:
    print("\n[ Listening... speak now ]")
    audio = recognizer.listen(source, timeout=6, phrase_time_limit=phrase_limit)

    text = recognizer.recognize_google(audio).lower()
    print(f"[ Google Heard: '{text}' ]")
    return text
  except sr.WaitTimeoutError:
    return ""
  except sr.UnknownValueError:
    print("[ Unrecognized audio / background noise ]")
    return ""
  except sr.RequestError as e:
    print(f"[ Speech API Error: {e} ]")
    return ""


def send_message_with_retry(chat, prompt, max_retries=3):
  """Sends prompt to Gemini with exponential backoff for 503/server spikes."""
  for attempt in range(max_retries):
    try:
      return chat.send_message_stream(prompt)
    except APIError as e:
      if e.code == 503 and attempt < max_retries - 1:
        print(
            f"\n[ 503 High Demand - retrying in {2 ** attempt}s... ]",
            flush=True,
        )
        time.sleep(2**attempt)
      else:
        raise e


def run_assistant():
  global MODEL
  MODEL = pick_model(client)

  r = sr.Recognizer()
  r.pause_threshold = 0.8
  r.dynamic_energy_threshold = True

  WAKE_WORD = "slice"
  EXIT_WORDS = ["stop", "exit", "quit", "goodbye", "bye", "reset"]

  print("==================================================")
  print(f" Assistant Online. Waiting for wake word: '{WAKE_WORD}'")
  print("==================================================")

  with suppress_c_stderr():
    mic = sr.Microphone()

  with mic as source:
    # Calibrate ambient noise ONCE at startup
    print("\n[ Calibrating microphone for ambient noise... ]")
    r.adjust_for_ambient_noise(source, duration=1.0)

    while True:
      # PHASE 1: PASSIVE LISTENING (Wake Word Detection)
      print(f"\n[ Sleeping... Say '{WAKE_WORD}' to wake up ]")
      transcript = listen_for_audio(r, source, phrase_limit=4)

      if WAKE_WORD in transcript:
        speak("I am listening")

        # Model is resolved once at startup; reuse it for every session.
        chat = client.chats.create(
            model=MODEL, config={"temperature": 0.7}
        )

        # PHASE 2: ACTIVE CONVERSATION LOOP
        while True:
          user_input = listen_for_audio(r, source, phrase_limit=12)

          if not user_input:
            continue

          print(f"\nYou: {user_input}")

          if any(exit_word in user_input for exit_word in EXIT_WORDS):
            speak("Goodbye! Call me if you need anything else.")
            break

          print("AI (Thinking...): ", end="", flush=True)

          try:
            response_stream = send_message_with_retry(chat, user_input)
            full_response = ""
            for chunk in response_stream:
              if chunk.text:
                print(chunk.text, end="", flush=True)
                full_response += chunk.text
            print()

            speak(full_response)
          except Exception as e:
            print(f"\n[ API Response Error: {e} ]")
            speak("Sorry, I encountered an issue connecting to the server.")

      time.sleep(0.1)


if __name__ == "__main__":
  try:
    run_assistant()
  except KeyboardInterrupt:
    print("\nExiting Assistant.")
    sys.exit(0)