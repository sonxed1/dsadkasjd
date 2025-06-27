from flask import Flask, request
import discord
from discord.ext import commands
import asyncio
import requests
from threading import Thread
import time
import os
from pytube import YouTube
import re

# Flask setup
app = Flask(__name__)

# Discord setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Config
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
SECRET_TOKEN = os.environ["SECRET_TOKEN"]
YOUR_USER_ID = 144258243772940289
FRIEND_USER_ID = 323976926777835533
allowed_user_ids = [YOUR_USER_ID, FRIEND_USER_ID]

AGENT_LINKS = {
    str(YOUR_USER_ID): "secondlife:///app/agent/fdf2125c-7149-44e6-aacf-24f1006fbbd6/about",
    str(FRIEND_USER_ID): "secondlife:///app/agent/05be3255-01f9-4977-b618-07c6ad9c5209/about"
}

SL_URL = "http://simhost-06efdb803b0a6b13a.agni.secondlife.io:12046/cap/8c5e5260-497e-d8e3-c59a-9c16e2fe1397"

presence_tracker = {
    "fdf2125c-7149-44e6-aacf-24f1006fbbd6": {"last_seen": 0, "online": False, "discord_id": YOUR_USER_ID},
    "05be3255-01f9-4977-b618-07c6ad9c5209": {"last_seen": 0, "online": False, "discord_id": FRIEND_USER_ID}
}

# Flask Routes
@app.route('/')
def home():
    return "Bot is running!"

@app.route('/update_sl_url', methods=['POST'])
def update_sl_url():
    token = request.form.get('token')
    if token != SECRET_TOKEN:
        return "Unauthorized", 401
    global SL_URL
    SL_URL = request.form['sl_url']
    print(f"Updated SL_URL to: {SL_URL}")
    return "OK"

@app.route('/send_message', methods=['POST'])
def send_message():
    message = request.form['message']
    sender = request.form['sender']
    sender_uuid = request.form['sender_uuid']
    formatted_message = f"{sender}: {message}"
    recipients = []

    if sender_uuid == "fdf2125c-7149-44e6-aacf-24f1006fbbd6":
        if not presence_tracker["05be3255-01f9-4977-b618-07c6ad9c5209"]["online"]:
            recipients.append(FRIEND_USER_ID)
    elif sender_uuid == "05be3255-01f9-4977-b618-07c6ad9c5209":
        if not presence_tracker["fdf2125c-7149-44e6-aacf-24f1006fbbd6"]["online"]:
            recipients.append(YOUR_USER_ID)
    else:
        for uuid, data in presence_tracker.items():
            if not data["online"]:
                recipients.append(data["discord_id"])

    if recipients:
        asyncio.run_coroutine_threadsafe(send_dm(recipients, formatted_message), bot.loop)
    return "OK"

@app.route('/visitor_update', methods=['POST'])
def visitor_update():
    arrivals = [a.strip() for a in request.form.get('arrivals', '').split(',') if a.strip()]
    departures = [d.strip() for d in request.form.get('departures', '').split(',') if d.strip()]

    for arrival in arrivals:
        formatted_name, profile_url = parse_visitor_name(arrival)
        linked_name = f"[{formatted_name}]({profile_url})"
        message = f"👋 New visitor: {linked_name} has entered the area!"
        asyncio.run_coroutine_threadsafe(send_dm([YOUR_USER_ID, FRIEND_USER_ID], message), bot.loop)

    for departure in departures:
        formatted_name, profile_url = parse_visitor_name(departure)
        linked_name = f"[{formatted_name}]({profile_url})"
        message = f"👋 {linked_name} has left the area!"
        asyncio.run_coroutine_threadsafe(send_dm([YOUR_USER_ID, FRIEND_USER_ID], message), bot.loop)

    return "OK"

@app.route('/update_presence', methods=['POST'])
def update_presence():
    avatars_present = [uuid.strip() for uuid in request.form.get('avatars_present', '').split(',') if uuid.strip()]
    current_time = time.time()

    for uuid in avatars_present:
        if uuid in presence_tracker:
            presence_tracker[uuid]["last_seen"] = current_time
            presence_tracker[uuid]["online"] = True

    for uuid in presence_tracker:
        if uuid not in avatars_present:
            presence_tracker[uuid]["online"] = False

    return "OK"

# Helpers
def parse_visitor_name(raw_name):
    if '(' in raw_name:
        formatted_name = raw_name.rsplit('(', 1)[0].strip()
        username = raw_name.split('(')[-1].split(')')[0].strip()
    else:
        formatted_name = raw_name
        username = raw_name

    if username.lower().endswith(" resident"):
        profile_username = username[:-9].strip()
    else:
        profile_username = username.replace(" ", ".")

    profile_url = "https://my.secondlife.com/" + profile_username.lower()
    return formatted_name, profile_url

async def send_dm(user_ids, message):
    for user_id in user_ids:
        user = await bot.fetch_user(user_id)
        if user:
            await user.send(message)

def is_valid_youtube_url(url):
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url) is not None

# Bot events
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.DMChannel) and message.author.id in allowed_user_ids:
        if message.content.startswith("!play "):
            await handle_play(message)
        elif message.content == "!stop":
            await handle_stop(message)
        else:
            await handle_text(message)

async def handle_play(message):
    url = message.content.split(" ", 1)[1]
    if not is_valid_youtube_url(url):
        await message.channel.send("❌ Please provide a valid YouTube URL")
        return
    try:
        yt = YouTube(url)
        audio_stream = yt.streams.filter(only_audio=True, file_extension='mp4').order_by('abr').desc().first()
        if audio_stream:
            audio_url = audio_stream.url
            print(f"Sending audio to SL: {audio_url}")
            response = requests.post(SL_URL, data={"message": f"PLAY_AUDIO:{audio_url}"}, timeout=10)
            if response.status_code == 200:
                await message.channel.send("🎵 Playing audio in Second Life!")
            else:
                await message.channel.send(f"🚨 Error: HTTP {response.status_code} - {response.text}")
        else:
            await message.channel.send("❌ Couldn't find audio stream for this video")
    except Exception as e:
        await message.channel.send(f"🚨 Error: {str(e)}")

async def handle_stop(message):
    response = requests.post(SL_URL, data={"message": "STOP_AUDIO"}, timeout=5)
    print(f"Stop command sent. Status: {response.status_code}")
    await message.channel.send("⏹️ Stopped audio in Second Life")

async def handle_text(message):
    agent_link = AGENT_LINKS.get(str(message.author.id), message.author.name)
    msg_to_send = f"{agent_link} (on Discord): {message.content}"
    if message.attachments:
        attachments_str = ", ".join([a.url for a in message.attachments])
        msg_to_send += f"\nAttachments: {attachments_str}"

    response = requests.post(SL_URL, data={"message": msg_to_send}, timeout=5)
    print(f"Message sent to SL. Status: {response.status_code}")

# Presence checker
def check_presence():
    while True:
        current_time = time.time()
        for uuid, data in presence_tracker.items():
            if current_time - data["last_seen"] > 300:
                data["online"] = False
        time.sleep(60)

# Start Flask server
def run():
    app.run(host="0.0.0.0", port=8080)

# Main
if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=check_presence, daemon=True).start()
    asyncio.run(bot.start(DISCORD_TOKEN))
