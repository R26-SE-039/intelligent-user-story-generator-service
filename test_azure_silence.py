import time
import azure.cognitiveservices.speech as speechsdk
import os

speech_key = "5A2DWpclYgECCc7H3A7RVTmessjZ8o7jkKj9eU90hziB1YcdmpWTJQQJ99CEACqBBLyXJ3w3AAAYACOGDdr6"
service_region = "southeastasia"

speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
stream_format = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
push_stream = speechsdk.audio.PushAudioInputStream(stream_format)
audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

def recognizing_cb(evt):
    print("RECOGNIZING:", evt.result.text)

def recognized_cb(evt):
    print("RECOGNIZED:", evt.result.text, evt.result.reason)

def canceled_cb(evt):
    print("CANCELED:", evt.reason, evt.error_details)

recognizer.recognizing.connect(recognizing_cb)
recognizer.recognized.connect(recognized_cb)
recognizer.canceled.connect(canceled_cb)

recognizer.start_continuous_recognition_async().get()
print("Recognizer started")

# Feed silence
zeros = bytes([0] * 32000) # 1 sec of silence
for i in range(10):
    push_stream.write(zeros)
    time.sleep(1)
    print(f"Pushed {i} seconds")

recognizer.stop_continuous_recognition_async().get()
print("Done")
