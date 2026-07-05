import requests
import os

speech_key = "5A2DWpclYgECCc7H3A7RVTmessjZ8o7jkKj9eU90hziB1YcdmpWTJQQJ99CEACqBBLyXJ3w3AAAYACOGDdr6"
service_region = "southeastasia"

url = f"https://{service_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=en-US"

headers = {
    "Ocp-Apim-Subscription-Key": speech_key,
    "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
    "Accept": "application/json"
}

with open("debug_audio.wav", "rb") as f:
    audio_data = f.read()

print(f"Sending {len(audio_data)} bytes to Azure REST API...")
response = requests.post(url, headers=headers, data=audio_data)

print("Status Code:", response.status_code)
print("Response:", response.text)
