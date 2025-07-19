import speech_recognition as sr

r = sr.Recognizer()
with sr.Microphone() as source:
    print("Say something!")
    audio = r.listen(source)
    print("Audio captured, sending to Google...")
    try:
        print("You said: " + r.recognize_google(audio))#type: ignore
    except Exception as e:
        print("Error:", e)