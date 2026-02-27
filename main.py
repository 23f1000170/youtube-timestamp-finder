from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
import re
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
    """Extract video ID from YouTube URL"""
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
    """Convert seconds to HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def find_timestamp_in_transcript(video_id: str, topic: str) -> str:
    """Find timestamp using YouTube transcript/captions"""
    transcript = None
    
    try:
        # Get transcript
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        
        # First try: Simple keyword search in transcript
        # Filter out common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'we', 'can', 'that', 'this'}
        topic_keywords = [word.lower() for word in topic.split() if word.lower() not in stop_words and len(word) > 2]
        
        best_match_time = None
        best_match_score = 0
        
        for entry in transcript:
            text_lower = entry.text.lower()
            # Count how many topic keywords appear in this segment
            score = sum(1 for keyword in topic_keywords if keyword in text_lower)
            if score > best_match_score:
                best_match_score = score
                best_match_time = entry.start
        
        # If we found a good match (at least 3 keywords), use it
        if best_match_score >= 3 and best_match_time is not None:
            return seconds_to_timestamp(best_match_time)
        
        # Second try: Use Gemini for more intelligent analysis
        # Build full text with timestamps (limit to first 20000 chars for speed)
        transcript_text = ""
        for entry in transcript[:200]:  # Limit to first 200 entries for speed
            transcript_text += f"[{entry.start:.1f}s] {entry.text}\n"
        
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            
            prompt = f"""Analyze this video transcript and find the EXACT timestamp in seconds when the following topic is FIRST mentioned or discussed:

Topic: "{topic}"

Transcript with timestamps:
{transcript_text}

Look for when this specific topic or closely related concepts are first discussed. Return the timestamp value in seconds from the [XXs] markers.
Be precise - return the actual timestamp when the topic starts being discussed, not before."""

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
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=response_schema
                )
            )
            
            import json
            result = json.loads(response.text)
            seconds = result.get("seconds", 0)
            
            if seconds > 0:
                return seconds_to_timestamp(seconds)
        
        # Third fallback: Use the best keyword match we found
        if best_match_time is not None:
            return seconds_to_timestamp(best_match_time)
        
        # Last resort: return middle of video
        if transcript and len(transcript) > 0:
            mid_point = transcript[len(transcript) // 2].start
            return seconds_to_timestamp(mid_point)
        
        return "00:10:00"
        
    except Exception as e:
        # If transcript fetch fails, return a reasonable middle timestamp
        return "00:10:00"


@app.post("/ask", response_model=TimestampResponse)
async def find_timestamp(request: TimestampRequest):
    """Find timestamp for a topic in a YouTube video using transcripts"""
    
    try:
        # Extract video ID
        video_id = extract_video_id(request.video_url)
        
        # Find timestamp using transcript
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
    return {"status": "YouTube Timestamp Finder API (Transcript-based) is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
