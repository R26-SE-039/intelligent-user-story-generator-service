import azure.cognitiveservices.speech as speechsdk
import time

speech_key = "5A2DWpclYgECCc7H3A7RVTmessjZ8o7jkKj9eU90hziB1YcdmpWTJQQJ99CEACqBBLyXJ3w3AAAYACOGDdr6"
service_region = "southeastasia"

speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
speech_config.speech_recognition_language = "en-US"

audio_config = speechsdk.audio.AudioConfig(filename="synth.wav")
recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

done = False
def recognizing_cb(evt):
    print("RECOGNIZING:", evt.result.text)

def recognized_cb(evt):
    print("RECOGNIZED:", evt.result.text)

def canceled_cb(evt):
    print("CANCELED:", evt.reason)

def stopped_cb(evt):
    print("STOPPED")
    global done
    done = True

recognizer.recognizing.connect(recognizing_cb)
recognizer.recognized.connect(recognized_cb)
recognizer.canceled.connect(canceled_cb)
recognizer.session_stopped.connect(stopped_cb)

recognizer.start_continuous_recognition_async().get()

while not done:
    time.sleep(0.5)
