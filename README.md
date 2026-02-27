# YouTube Timestamp Finder API

FastAPI endpoint that finds timestamps for topics in YouTube videos using Gemini audio processing.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set your Gemini API key in `.env`:
```
GEMINI_API_KEY=your_api_key_here
```

3. Install FFmpeg (required by yt-dlp for audio extraction):
   - Windows: Download from https://ffmpeg.org/download.html
   - Or use: `choco install ffmpeg`

## Running the API

```bash
python main.py
```

The API will run on `http://localhost:8000`

## API Endpoint

### POST /ask

Find the timestamp when a topic is mentioned in a YouTube video.

**Request:**
```json
{
  "video_url": "https://youtu.be/dQw4w9WgXcQ",
  "topic": "the spoken phrase or subject to locate"
}
```

**Response:**
```json
{
  "timestamp": "00:05:47",
  "video_url": "https://youtu.be/dQw4w9WgXcQ",
  "topic": "the spoken phrase or subject to locate"
}
```

## Testing

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://youtu.be/dQw4w9WgXcQ",
    "topic": "never gonna give you up"
  }'
```

## How It Works

1. **Audio Download**: Uses `yt-dlp` to download audio-only from YouTube (avoids the 10,800 image frame limit)
2. **File Upload**: Uploads audio to Gemini Files API
3. **Processing Wait**: Polls until file state becomes ACTIVE
4. **Timestamp Detection**: Uses Gemini with structured output to find the timestamp in HH:MM:SS format
5. **Cleanup**: Removes temporary audio files

## Deployment

For production deployment with ngrok:

```bash
ngrok http 8000
```

Then use the ngrok URL (e.g., `https://abc.ngrok.io`) as your endpoint.

## Key Features

- ✅ Audio-only download (no video frames)
- ✅ Gemini Files API integration
- ✅ Structured output for consistent HH:MM:SS format
- ✅ Automatic file cleanup
- ✅ File state polling before processing
- ✅ Error handling for failed downloads/uploads
