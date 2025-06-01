#!/usr/bin/env python3

"""
YouTube Audio Downloader

This script downloads audio from YouTube videos in opus format. It handles authentication
through browser cookies to avoid bot detection and supports various audio formats.

Features:
- Downloads audio-only when available to minimize bandwidth
- Converts to opus format (or other formats as configured)
- Uses browser cookies for authentication
- Supports format listing
- Handles various YouTube errors gracefully

Usage:
    python audio_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python audio_downloader.py --list-formats "https://www.youtube.com/watch?v=VIDEO_ID"
"""

import sys
import os
import json
import tempfile
import glob
import time
import random
from pathlib import Path
import yt_dlp

# Type hints for better code understanding
from typing import Optional, Dict, List, Any, Tuple

class YouTubeAudioDownloader:
    """Main class for handling YouTube audio downloads."""
    
    def __init__(self, settings_file: str = 'settings.json'):
        """Initialize the downloader with settings.
        
        Args:
            settings_file: Path to the settings JSON file
        """
        self.settings = self._load_settings(settings_file)
        self.cookie_file = None
        self.using_temp_file = False
    
    @staticmethod
    def _load_settings(settings_file: str) -> Dict[str, Any]:
        """Load settings from JSON file.
        
        Args:
            settings_file: Path to the settings file
            
        Returns:
            Dictionary containing the settings
            
        Raises:
            SystemExit: If settings file is not found or invalid
        """
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
            
            # Expand the download directory path if it contains ~
            settings['download_directory'] = os.path.expanduser(settings['download_directory'])
            
            # Set default cookie settings if not present
            if 'cookies' not in settings:
                settings['cookies'] = {
                    'use_browser_cookies': True,
                    'custom_cookies_file': None
                }
            
            return settings
        except FileNotFoundError:
            print("Error: settings.json file not found!")
            print("Please create a settings.json file with the following format:")
            print('''{
    "download_directory": "~/Music/YouTube",
    "audio_format": "opus",
    "audio_quality": "best",
    "create_directory_if_missing": true,
    "show_progress": true,
    "cookies": {
        "use_browser_cookies": true,
        "custom_cookies_file": null
    }
}''')
            sys.exit(1)
        except json.JSONDecodeError:
            print("Error: settings.json is not valid JSON!")
            sys.exit(1)

    @staticmethod
    def _get_random_user_agent() -> str:
        """Get a random user agent string to avoid bot detection."""
        user_agents = [
            # Chrome on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            # Firefox on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0',
            # Safari on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15'
        ]
        return random.choice(user_agents)

    def _get_base_options(self, cookie_file: Optional[str] = None) -> Dict[str, Any]:
        """Get base options for yt-dlp.
        
        Args:
            cookie_file: Optional path to cookie file
            
        Returns:
            Dictionary of yt-dlp options
        """
        options = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': self._get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }
        }
        
        if cookie_file:
            options['cookiefile'] = cookie_file
        
        return options

    def _find_firefox_cookie_file(self) -> Optional[str]:
        """Try to find Firefox cookie file on macOS.
        
        Returns:
            Path to cookie file if found, None otherwise
        """
        firefox_profile_path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        if os.path.exists(firefox_profile_path):
            profiles = glob.glob(os.path.join(firefox_profile_path, "*.default*"))
            if profiles:
                cookie_file = os.path.join(profiles[0], "cookies.sqlite")
                if os.path.exists(cookie_file):
                    return cookie_file
        return None

    def _save_cookies_to_file(self, cookies: Any) -> Optional[str]:
        """Save browser cookies to a temporary file in Netscape format.
        
        Args:
            cookies: Cookie object from browser_cookie3
            
        Returns:
            Path to temporary cookie file if successful, None otherwise
        """
        cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        try:
            # Write header required by Netscape format
            cookie_file.write("# Netscape HTTP Cookie File\n")
            cookie_file.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
            cookie_file.write("# This is a generated file!  Do not edit.\n\n")
            
            # Convert browser_cookie3 cookies to Netscape format
            current_time = int(time.time())
            for cookie in cookies:
                # Handle missing expiration by setting it to 1 year from now
                expires = cookie.expires if cookie.expires else current_time + 31536000
                
                # Ensure all fields are properly formatted
                domain = cookie.domain if cookie.domain.startswith('.') else '.' + cookie.domain
                path = cookie.path if cookie.path else '/'
                secure = 'TRUE' if cookie.secure else 'FALSE'
                
                cookie_file.write(f"{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{cookie.name}\t{cookie.value}\n")
            
            cookie_file.close()
            return cookie_file.name
        except Exception as e:
            print(f"Error saving cookies: {str(e)}")
            try:
                os.unlink(cookie_file.name)
            except:
                pass
            return None

    def _get_browser_cookies(self) -> Optional[str]:
        """Get cookies from installed browsers.
        
        Returns:
            Path to cookie file if successful, None otherwise
        """
        import browser_cookie3
        
        browsers = {
            'Chrome': browser_cookie3.chrome,
            'Firefox': browser_cookie3.firefox,
            'Edge': browser_cookie3.edge
        }
        
        for browser_name, browser_func in browsers.items():
            try:
                cookies = browser_func(domain_name='.youtube.com')
                print(f"Successfully loaded cookies from {browser_name}")
                cookie_file = self._save_cookies_to_file(cookies)
                if cookie_file:
                    print(f"Successfully saved cookies to temporary file")
                    return cookie_file
                print(f"Failed to save cookies from {browser_name}")
            except Exception as e:
                if "could not find" in str(e):
                    print(f"No {browser_name} cookies found")
                    if browser_name == 'Firefox' and sys.platform == 'darwin':
                        firefox_cookie = self._find_firefox_cookie_file()
                        if firefox_cookie:
                            print(f"Found Firefox cookies at: {firefox_cookie}")
                            print("You can set this path in settings.json as custom_cookies_file")
                else:
                    print(f"Error accessing {browser_name} cookies: {str(e)}")
                continue
        
        print("\nWarning: Could not load cookies from any browser.")
        print("\nMake sure you have at least one of these browsers installed and are logged into YouTube:")
        print("- Chrome")
        print("- Firefox")
        print("- Edge")
        return None

    def _get_cookies(self) -> Tuple[Optional[str], bool]:
        """Get cookies based on settings.
        
        Returns:
            Tuple of (cookie_file_path, is_temporary_file)
        """
        # Check if custom cookies file is specified
        if self.settings['cookies']['custom_cookies_file']:
            cookie_path = os.path.expanduser(self.settings['cookies']['custom_cookies_file'])
            if os.path.exists(cookie_path):
                print(f"Using custom cookies file: {cookie_path}")
                return cookie_path, False
            else:
                print(f"Warning: Custom cookies file not found at {cookie_path}")
        
        # Fall back to browser cookies if enabled
        if self.settings['cookies']['use_browser_cookies']:
            print("Attempting to load cookies from browsers...")
            cookie_file = self._get_browser_cookies()
            return cookie_file, bool(cookie_file and cookie_file.startswith(tempfile.gettempdir()))
        
        print("No valid cookie source configured. Some videos might be unavailable.")
        return None, False

    def list_formats(self, url: str, cookie_file: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """List all available formats for a video.
        
        Args:
            url: YouTube video URL
            cookie_file: Optional path to cookie file
            
        Returns:
            List of format dictionaries if successful, None otherwise
        """
        ydl_opts = self._get_base_options(cookie_file)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                
                if not formats:
                    print("No formats available for this video.")
                    return None
                
                print("\nAvailable formats:")
                print("Format Code  Extension  Resolution/Bitrate  Filesize    Note")
                print("-" * 80)
                
                audio_formats = []
                video_formats = []
                
                for f in formats:
                    format_id = f.get('format_id', 'N/A')
                    ext = f.get('ext', 'N/A')
                    
                    # Get resolution or bitrate
                    if f.get('vcodec') == 'none':  # Audio only
                        quality = f"{f.get('abr', 'N/A')}k"
                        audio_formats.append((format_id, ext, quality, f))
                    else:  # Video
                        quality = f.get('resolution', 'N/A')
                        video_formats.append((format_id, ext, quality, f))
                
                # Print audio formats first
                if audio_formats:
                    print("\nAudio-only formats:")
                    for format_id, ext, quality, f in audio_formats:
                        filesize = f.get('filesize', 'N/A')
                        if filesize != 'N/A':
                            filesize = f"{filesize/1024/1024:.1f}MB"
                        note = f.get('format_note', '')
                        print(f"{format_id:11} {ext:9} {quality:16} {filesize:10} {note}")
                
                # Then print video formats
                if video_formats:
                    print("\nVideo formats (with audio if available):")
                    for format_id, ext, quality, f in video_formats:
                        filesize = f.get('filesize', 'N/A')
                        if filesize != 'N/A':
                            filesize = f"{filesize/1024/1024:.1f}MB"
                        note = f.get('format_note', '')
                        print(f"{format_id:11} {ext:9} {quality:16} {filesize:10} {note}")
                
                return formats
            except Exception as e:
                print(f"Error listing formats: {str(e)}")
                return None

    def download(self, url: str) -> None:
        """Download audio from a YouTube video.
        
        Args:
            url: YouTube video URL
        """
        # Create download directory if it doesn't exist and setting is enabled
        if self.settings['create_directory_if_missing']:
            Path(self.settings['download_directory']).mkdir(parents=True, exist_ok=True)
        
        # Get cookies based on settings
        self.cookie_file, self.using_temp_file = self._get_cookies()
        
        try:
            # If --list-formats is specified, just list formats and exit
            if '--list-formats' in sys.argv:
                self.list_formats(url, self.cookie_file)
                return
            
            # Get base options and add download-specific options
            ydl_opts = self._get_base_options(self.cookie_file)
            ydl_opts.update({
                'format': 'bestaudio[ext=opus]/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                'quiet': not self.settings['show_progress'],
                'retries': 10,  # Retry up to 10 times
                'fragment_retries': 10,
                'skip_unavailable_fragments': False,
                'ignoreerrors': False
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    print("Checking video availability...")
                    info = ydl.extract_info(url, download=False)
                    print(f"Video found: {info.get('title', 'Unknown title')}")
                    
                    # Check available formats
                    formats = info.get('formats', [])
                    best_format = None
                    for f in formats:
                        if f.get('vcodec') == 'none':  # Audio only format
                            acodec = f.get('acodec', '').lower()
                            if acodec == 'opus':
                                print("Found opus audio format - perfect match!")
                                best_format = f
                                break
                            elif not best_format and acodec in ['m4a', 'mp4a', 'aac']:
                                best_format = f
                    
                    if best_format:
                        if best_format.get('acodec', '').lower() == 'opus':
                            print("Will download opus directly - no conversion needed")
                        else:
                            print(f"Found audio-only format ({best_format.get('acodec')}) - minimal conversion needed")
                    else:
                        print("No audio-only format available - will extract audio from video")
                    
                    print("\nStarting download...")
                    info = ydl.extract_info(url, download=True)
                    downloaded_file = ydl.prepare_filename(info)
                    
                    # If the downloaded file is not already in opus format, convert it
                    if not downloaded_file.endswith('.opus'):
                        output_file = os.path.splitext(downloaded_file)[0] + '.opus'
                        print(f"\nConverting to opus format...")
                        import subprocess
                        
                        try:
                            # Run ffmpeg with detailed error output
                            result = subprocess.run([
                                'ffmpeg',
                                '-i', downloaded_file,
                                '-c:a', 'libopus',
                                '-b:a', '192k',
                                '-ar', '48000',
                                '-ac', '2',
                                '-v', 'warning',
                                output_file
                            ], capture_output=True, text=True, check=True)
                            
                            # Remove the original file if conversion was successful
                            os.unlink(downloaded_file)
                            print("Conversion completed successfully!")
                            
                        except subprocess.CalledProcessError as e:
                            print(f"Error during conversion: {e.stderr}")
                            if os.path.exists(output_file):
                                os.unlink(output_file)
                            raise Exception("Audio conversion failed. See error details above.")
                        except Exception as e:
                            print(f"Unexpected error during conversion: {str(e)}")
                            if os.path.exists(output_file):
                                os.unlink(output_file)
                            raise
                    
                    print(f"\nDownload completed! File saved in: {self.settings['download_directory']}")
                except Exception as e:
                    if "Sign in to confirm you're not a bot" in str(e):
                        print("\nError: YouTube is requesting verification.")
                        print("Please try the following:")
                        print("1. Make sure you're logged into YouTube in your browser")
                        print("2. Try opening the video in your browser first")
                        print("3. Wait a few minutes and try again")
                        print("4. If using Firefox, try using Chrome or Safari instead")
                        sys.exit(1)
                    elif "Requested format is not available" in str(e):
                        print("\nError: Could not find suitable audio format.")
                        formats = self.list_formats(url, self.cookie_file)
                        if formats:
                            print("\nTry using a different format or video URL.")
                        sys.exit(1)
                    elif "HTTP Error 403: Forbidden" in str(e):
                        print("\nError: Access forbidden by YouTube.")
                        print("This might be due to:")
                        print("1. Too many requests - wait a few minutes and try again")
                        print("2. Region restrictions - try with a different video")
                        print("3. Age-restricted content - make sure you're logged in")
                        sys.exit(1)
                    raise e
        except Exception as e:
            print(f"Error downloading video: {str(e)}")
            if "HTTP Error 403" in str(e):
                print("\nTip: YouTube blocked the request. Try:")
                print("1. Waiting a few minutes before trying again")
                print("2. Using a different browser's cookies")
                print("3. Opening the video in your browser first")
            sys.exit(1)
        finally:
            # Clean up the temporary cookie file only if we created it
            if self.using_temp_file and self.cookie_file and os.path.exists(self.cookie_file):
                try:
                    os.unlink(self.cookie_file)
                except:
                    pass

def main():
    """Main entry point of the script."""
    if len(sys.argv) < 2:
        print("Usage: python audio_downloader.py [--list-formats] <youtube-url>")
        sys.exit(1)
    
    url = sys.argv[-1]  # Get the last argument as the URL
    downloader = YouTubeAudioDownloader()
    downloader.download(url)

if __name__ == "__main__":
    main() 