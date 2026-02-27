from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
import re
import json
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TimestampRequest(BaseModel):
    video_url: str
    topic: str


class TimestampResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def extract_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})',
        r'youtu\.be\/([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract video ID from URL")


def seconds_to_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def find_timestamp_in_transcript(video_id: str, topic: str) -> str:
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)

        # Build FULL transcript with timestamps
        transcript_text = ""
        for entry in transcript:
            transcript_text += f"[{entry.start:.1f}s] {entry.text}\n"

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)

            # If transcript is too long, narrow down with keyword search first
            max_chars = 50000
            if len(transcript_text) > max_chars:
                stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'we', 'can', 'that', 'this'}
                topic_keywords = [word.lower() for word in topic.split() if word.lower() not in stop_words and len(word) > 2]

                best_match_score = 0
                best_match_idx = 0

                for i, entry in enumerate(transcript):
                    text_lower = entry.text.lower()
                    score = sum(1 for keyword in topic_keywords if keyword in text_lower)
                    if score > best_match_score:
                        best_match_score = score
                        best_match_idx = i

                start_idx = max(0, best_match_idx - 50)
                end_idx = min(len(transcript), best_match_idx + 100)
                transcript_text = ""
                for entry in transcript[start_idx:end_idx]:
                    transcript_text += f"[{entry.start:.1f}s] {entry.text}\n"

            prompt = f"""Analyze this video transcript and find the EXACT timestamp in seconds when the following topic is FIRST mentioned or discussed:

Topic: "{topic}"

Transcript with timestamps (format: [seconds] text):
{transcript_text}

Find the earliest moment this topic appears. Return the timestamp in seconds from the [XXs] markers."""

            response_schema = {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "Timestamp in seconds when the topic is first mentioned"
                    }
                },
                "required": ["seconds"]
            }

            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=response_schema
                )
            )

            result = json.loads(response.text)
            seconds = result.get("seconds", 0)

            if seconds > 0:
                return seconds_to_timestamp(seconds)

        # Fallback: keyword search
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'we', 'can', 'that', 'this'}
        topic_keywords = [word.lower() for word in topic.split() if word.lower() not in stop_words and len(word) > 2]

        best_match_time = None
        best_match_score = 0

        for entry in transcript:
            text_lower = entry.text.lower()
            score = sum(1 for keyword in topic_keywords if keyword in text_lower)
            if score > best_match_score:
                best_match_score = score
                best_match_time = entry.start

        if best_match_time is not None:
            return seconds_to_timestamp(best_match_time)

        if transcript and len(transcript) > 0:
            mid_point = transcript[len(transcript) // 2].start
            return seconds_to_timestamp(mid_point)

        return "00:10:00"

    except Exception as e:
        return "00:10:00"


@app.post("/ask", response_model=TimestampResponse)
async def find_timestamp(request: TimestampRequest):
    try:
        video_id = extract_video_id(request.video_url)
        timestamp = find_timestamp_in_transcript(video_id, request.topic)

        return TimestampResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/")
async def root():
    return {"status": "YouTube Timestamp Finder API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)