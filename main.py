"""Daily kids video: Gemini script -> safety check -> render -> YouTube upload."""
import json
import os
import random
import sys
import time
import urllib.request

import render  # render.py: edge-tts + Pollinations images + FFmpeg

GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-2.5-flash:generateContent")
LANGUAGE = os.environ.get("LANGUAGE", "English")
VOICE = os.environ.get("VOICE", "en-US-AnaNeural")
PRIVACY = os.environ.get("PRIVACY", "private")
SCENES = int(os.environ.get("SCENE_COUNT", "8"))

CATEGORIES = [
    "Animals and their babies", "Colors and shapes", "Counting numbers 1 to 10",
    "Space and planets", "Bedtime story with a gentle ending", "Ocean life",
    "Fruits and vegetables", "Weather and seasons", "Vehicles and machines",
    "Dinosaurs", "Kindness and sharing", "The alphabet", "Farm animals",
    "Insects and bugs", "Healthy habits like brushing teeth", "Musical instruments",
]


def gemini_json(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 1},
    }).encode()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(GEMINI_URL, data=body, headers={
                "Content-Type": "application/json",
                "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            })
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            last = e
            print(f"Gemini attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")


def write_script(category, recent):
    return gemini_json(
        f"You write short, safe, educational videos for children aged 3 to 7.\n"
        f"Language of the narration: {LANGUAGE}.\nCategory: {category}.\n"
        f"Choose ONE fresh, specific topic in this category that is NOT in this list: "
        f"{json.dumps(recent)}.\n"
        f"Write exactly {SCENES} scenes. Each narration is 2 or 3 short, simple, cheerful "
        f"sentences a child can follow.\n"
        f"Rules: nothing scary, violent, romantic, commercial or branded; no real people; "
        f"no existing cartoon characters; no medical advice.\n"
        'Return ONLY valid JSON: {"topic":"","title":"fun title under 70 characters with '
        'one emoji","description":"2-3 sentences for parents","tags":["8 to 12 tags"],'
        '"scenes":[{"narration":"","image_prompt":"English prompt: cute colorful flat '
        'cartoon illustration of ..., child friendly, soft colors, no text, no letters"}]}'
    )


def is_safe(script):
    verdict = gemini_json(
        "You are a strict child-safety reviewer for videos aimed at ages 3 to 7. "
        "It is UNSAFE if anything is scary, violent, sexual, hateful, political, "
        "commercial, brand-related, medical advice, mentions a real person or an "
        "existing copyrighted character, gives false facts, or is not age-appropriate. "
        'Return ONLY JSON: {"safe":true or false,"reason":"short reason"}.\n\nSCRIPT:\n'
        + json.dumps({"title": script["title"], "scenes": script["scenes"]})
    )
    return verdict.get("safe") is True, verdict.get("reason", "")


def upload(path, script):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds)
    request = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": script["title"][:95],
                "description": script["description"] + "\n\nMade with AI for kids.",
                "tags": script["tags"][:12],
                "categoryId": "27",
            },
            "status": {
                "privacyStatus": PRIVACY,
                "selfDeclaredMadeForKids": True,
            },
        },
        media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def main():
    history = json.load(open("history.json"))
    recent = [h["topic"] for h in history[-80:]]

    for attempt in range(3):
        category = random.choice(CATEGORIES)
        script = write_script(category, recent)
        script["scenes"] = [
            {"narration": str(s["narration"]), "image_prompt": str(s["image_prompt"])}
            for s in script["scenes"]
        ]
        if len(script["scenes"]) < 3:
            continue
        safe, reason = is_safe(script)
        topic = str(script.get("topic", category))
        if not safe:
            print(f"Rejected '{topic}': {reason}", flush=True)
            history.append({"topic": topic, "status": "rejected", "reason": reason})
            recent.append(topic)
            continue

        print(f"Rendering '{topic}'...", flush=True)
        video = render.render({"voice": VOICE, "scenes": script["scenes"]})
        with open("video.mp4", "wb") as f:
            f.write(video)
        video_id = upload("video.mp4", script)
        print(f"Uploaded: https://youtu.be/{video_id}", flush=True)
        history.append({"topic": topic, "status": "uploaded", "videoId": video_id})
        break
    else:
        print("No safe script after 3 tries; nothing uploaded today.", flush=True)

    json.dump(history[-300:], open("history.json", "w"), indent=2)


if __name__ == "__main__":
    sys.exit(main())
