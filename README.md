# YouTube Opus Downloader

A simple command-line tool to download YouTube videos as opus audio files.

Why Opus Format?

tl;dr \
Smaller files than MP3 while having the same quality. \
In ideal case, no video download or conversion (means also no conversion loss) needed.

- Opus is a modern, open-source audio codec designed for efficient streaming and storage
- Superior compression: Better quality at lower bitrates compared to MP3
- Lower latency: Ideal for streaming and real-time applications
- Wider frequency range: 8 Hz to 48 kHz (MP3 is limited to 16 Hz to 16 kHz)
- Better handling of speech and music in a single format
- Native format on YouTube, avoiding quality loss from transcoding

| Case                           | Downloads video? | Converts audio? | Renames only? |
| ------------------------------ | ---------------- | --------------- | ------------- |
| Audio-only stream (opus) found | ❌ No             | ❌ No            | ✅ Yes (maybe) |
| Audio-only (non-opus) found    | ❌ No             | ✅ Yes           | ❌ No          |
| Only video+audio available     | ✅ Yes            | ✅ Yes           | ❌ No          |



## Requirements

1. Python 3.x
2. FFmpeg (for audio conversion)
3. **A web browser (Chrome or Firefox) with:**
   - Active YouTube login
   - Recent YouTube activity (to avoid bot detection)
   
The program uses cookies from your browser to authenticate with YouTube. This is necessary for:
- Avoiding bot detection
- Accessing age-restricted content
- Downloading at full quality

## Installation

1. Clone this repository
2. Install the requirements:
```bash
pip install -r requirements.txt
```

## Configuration

The program uses a `settings.json` file for configuration. Here's what each setting does:

- `download_directory`: Where to save the downloaded files
- `audio_format`: The format to convert to (opus by default)
- `audio_quality`: Quality setting for the download
- `create_directory_if_missing`: Whether to create the download directory if it doesn't exist
- `show_progress`: Whether to show download progress
- `cookies`: Cookie settings for YouTube authentication
  - `use_browser_cookies`: Whether to try getting cookies from browsers automatically
  - `custom_cookies_file`: Path to a custom cookie file (optional)

### Browser Setup

1. Make sure you're logged into YouTube in either Chrome or Firefox
2. Use the browser regularly with YouTube (this helps avoid bot detection)
3. Keep the browser installed and your YouTube session active

The program will automatically try to use cookies from:
1. Chrome (if installed)
2. Firefox (if installed)
3. Edge (if installed)

Example `settings.json`:
```json
{
    "download_directory": "~/Music/YouTube",
    "audio_format": "opus",
    "audio_quality": "best",
    "create_directory_if_missing": true,
    "show_progress": true,
    "cookies": {
        "use_browser_cookies": true,
        "custom_cookies_file": null
    }
}
```

## Usage

Run the script with a YouTube URL:
```bash
python3 audio_downloader.py "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

To see available formats before downloading:
```bash
python3 audio_downloader.py --list-formats "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

### Troubleshooting

If you get errors about bot detection or forbidden access:
1. Make sure you're logged into YouTube in your browser
2. Try opening the video in your browser first
3. Wait a few minutes between downloads
4. If using Firefox and having issues, try Chrome instead

The opus file will be downloaded to your specified download directory. 
