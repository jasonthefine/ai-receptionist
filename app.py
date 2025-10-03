import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI

app = Flask(__name__)

# ====== CONFIG ======
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BUSINESS_NAME  = os.getenv("BUSINESS_NAME", "Demo Receptionist")
BUSINESS_INFO  = os.getenv("BUSINESS_INFO", """
Hours: Mon–Fri 9am–5pm.
Services: general inquiries, pricing estimates, scheduling call-backs.
If unsure, politely collect name, phone, and reason for calling.
""").strip()

# Voice settings (Amazon Polly voices)
VOICE_NAME = os.getenv("VOICE_NAME", "Polly.Joanna")  # e.g. Polly.Matthew, Polly.Ivy, Polly.Kevin
VOICE_LANG = os.getenv("VOICE_LANG", "en-US")

# In-memory conversation store keyed by CallSid (simple demo state)
CONV = {}

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = f"""
You are a courteous, concise phone receptionist for {BUSINESS_NAME}.
Use the facts below. If a fact is not in these docs, say you'll take a message.
Avoid long paragraphs. Speak plainly and helpfully.
---
{BUSINESS_INFO}
"""

def run_gpt(messages):
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=messages
    )
    return resp.choices[0].message.content.strip()

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get("CallSid")
    CONV[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]

    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/gather",
        method="POST",
        speech_timeout="auto"
    )
    gather.say(f"Hello, thanks for calling {BUSINESS_NAME}. How can I help you today?",
               voice=VOICE_NAME, language=VOICE_LANG)
    vr.append(gather)

    vr.say("I didn't catch that. One more time.",
           voice=VOICE_NAME, language=VOICE_LANG)
    vr.redirect("/voice")
    return Response(str(vr), mimetype="text/xml")

@app.route("/gather", methods=["POST"])
def gather():
    call_sid = request.form.get("CallSid")
    user_text = request.form.get("SpeechResult", "") or ""

    vr = VoiceResponse()

    if not user_text:
        gather = Gather(input="speech", action="/gather", method="POST", speech_timeout="auto")
        gather.say("Sorry, I didn't hear anything. Please tell me how I can help.",
                   voice=VOICE_NAME, language=VOICE_LANG)
        vr.append(gather)
        return Response(str(vr), mimetype="text/xml")

    # Append user turn
    history = CONV.get(call_sid, [{"role": "system", "content": SYSTEM_PROMPT}])
    history.append({"role": "user", "content": user_text})

    try:
        assistant_text = run_gpt(history)
    except Exception:
        assistant_text = ("I'm having trouble accessing our assistant right now. "
                          "Would you like me to take a message with your name and number?")

    # Save assistant turn
    history.append({"role": "assistant", "content": assistant_text})
    CONV[call_sid] = history

    # Speak answer, then keep the conversation going
    gather = Gather(input="speech", action="/gather", method="POST", speech_timeout="auto")
    gather.say(assistant_text, voice=VOICE_NAME, language=VOICE_LANG)
    gather.say("Anything else I can help you with?", voice=VOICE_NAME, language=VOICE_LANG)
    vr.append(gather)

    vr.say("Thanks for calling. Goodbye!", voice=VOICE_NAME, language=VOICE_LANG)
    return Response(str(vr), mimetype="text/xml")

@app.route("/goodbye", methods=["POST"])
def goodbye():
    vr = VoiceResponse()
    vr.say("Thanks for calling. Goodbye!", voice=VOICE_NAME, language=VOICE_LANG)
    vr.hangup()
    return Response(str(vr), mimetype="text/xml")

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

