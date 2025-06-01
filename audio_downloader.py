#!/usr/bin/env python3

"""
YouTube Audio Downloader

This script downloads audio from YouTube videos in opus format. It handles authentication
through browser cookies to avoid bot detection and supports various audio formats.

Features:
- Downloads audio-only when available to minimize bandwidth
- Converts to opus format (or other formats as configured)
- Uses browser cookies for authentication (supports Chrome, Firefox, and Edge)
- Supports format listing
- Handles various YouTube errors gracefully

Usage:
    python audio_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python audio_downloader.py --list-formats "https://www.youtube.com/watch?v=VIDEO_ID"

Settings (settings.json):
    download_directory: Where to save downloaded files
    audio_format: Target audio format (opus recommended)
    audio_quality: Quality setting for downloads
    create_directory_if_missing: Create download directory if it doesn't exist
    show_progress: Show download progress
    cookies:
        use_browser_cookies: Whether to use browser cookies
        custom_cookies_file: Path to custom cookie file (optional)
        preferred_browser: Browser to get cookies from ("chrome", "firefox", or "edge")
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
                    'custom_cookies_file': None,
                    'preferred_browser': 'chrome'
                }
            elif 'preferred_browser' not in settings['cookies']:
                settings['cookies']['preferred_browser'] = 'chrome'
            
            # Validate preferred_browser setting
            valid_browsers = ['chrome', 'firefox', 'edge']
            if settings['cookies']['preferred_browser'].lower() not in valid_browsers:
                print(f"Warning: Invalid preferred_browser '{settings['cookies']['preferred_browser']}'. Using 'chrome'.")
                settings['cookies']['preferred_browser'] = 'chrome'
            else:
                settings['cookies']['preferred_browser'] = settings['cookies']['preferred_browser'].lower()
            
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
        "custom_cookies_file": null,
        "preferred_browser": "chrome"
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
            print(f"\nUsing cookie file: {cookie_file}")
            options['cookiefile'] = cookie_file
        else:
            print("\nNo cookie file specified")
        
        return options

    def _find_firefox_cookie_file(self) -> Optional[str]:
        """Find Firefox cookie file based on the operating system.
        
        Returns:
            Path to cookie file if found, None otherwise
            
        Supported paths:
        - Linux: ~/.mozilla/firefox/xxxxxxxx.default-release/cookies.sqlite
        - macOS: ~/Library/Application Support/Firefox/Profiles/xxxxxxxx.default-release/cookies.sqlite
        - Windows: %APPDATA%/Mozilla/Firefox/Profiles/xxxxxxxx.default-release/cookies.sqlite
        """
        import platform
        
        system = platform.system().lower()
        
        if system == 'linux':
            firefox_profile_path = os.path.expanduser("~/.mozilla/firefox")
        elif system == 'darwin':  # macOS
            firefox_profile_path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        elif system == 'windows':
            firefox_profile_path = os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles')
        else:
            print(f"Warning: Unsupported operating system {system} for Firefox cookie detection")
            return None
            
        if not os.path.exists(firefox_profile_path):
            print(f"No Firefox profile directory found at: {firefox_profile_path}")
            return None
            
        # Look for default profile
        default_profiles = []
        try:
            for item in os.listdir(firefox_profile_path):
                if item.endswith('.default') or item.endswith('.default-release'):
                    profile_path = os.path.join(firefox_profile_path, item)
                    if os.path.isdir(profile_path):
                        default_profiles.append(profile_path)
        except Exception as e:
            print(f"Error reading Firefox profiles: {str(e)}")
            return None
            
        if not default_profiles:
            print("No Firefox default profile found")
            return None
            
        # Use the most recently modified profile if multiple exist
        if len(default_profiles) > 1:
            default_profiles.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            print(f"Multiple Firefox profiles found, using most recent: {os.path.basename(default_profiles[0])}")
            
        cookie_file = os.path.join(default_profiles[0], 'cookies.sqlite')
        if os.path.exists(cookie_file):
            print(f"Found Firefox cookies at: {cookie_file}")
            return cookie_file
            
        print(f"No cookies.sqlite found in Firefox profile: {default_profiles[0]}")
        return None

    def _convert_firefox_cookies_to_netscape(self, sqlite_file: str) -> Optional[str]:
        """Convert Firefox's SQLite cookie file to Netscape format.
        
        Args:
            sqlite_file: Path to Firefox's cookies.sqlite file
            
        Returns:
            Path to temporary Netscape format cookie file if successful, None otherwise
        """
        try:
            import sqlite3
            import tempfile
            import shutil
            
            # Create a temporary copy of the SQLite file since it might be locked by Firefox
            temp_sqlite = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
            shutil.copy2(sqlite_file, temp_sqlite.name)
            
            # Create a temporary file for the Netscape format cookies
            cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            
            # Write Netscape format header
            cookie_file.write("# Netscape HTTP Cookie File\n")
            cookie_file.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
            cookie_file.write("# This is a generated file!  Do not edit.\n\n")
            
            # Connect to the copy of the SQLite database
            conn = sqlite3.connect(temp_sqlite.name)
            cursor = conn.cursor()
            
            # Query to get cookies in Netscape format
            cursor.execute("""
                SELECT host, 
                       CASE 
                           WHEN host LIKE '.%' THEN 'TRUE'
                           ELSE 'FALSE'
                       END,
                       path,
                       isSecure,
                       expiry,
                       name,
                       value
                FROM moz_cookies
                WHERE host LIKE '%youtube.com'
            """)
            
            # Write each cookie in Netscape format
            for row in cursor.fetchall():
                host, is_domain, path, is_secure, expiry, name, value = row
                secure = "TRUE" if is_secure else "FALSE"
                
                # Ensure the host starts with a dot for domain cookies
                if is_domain == 'TRUE' and not host.startswith('.'):
                    host = '.' + host
                
                cookie_line = f"{host}\t{is_domain}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n"
                cookie_file.write(cookie_line)
            
            cursor.close()
            conn.close()
            cookie_file.close()
            
            # Clean up the temporary SQLite file
            os.unlink(temp_sqlite.name)
            
            return cookie_file.name
            
        except Exception as e:
            print(f"Error converting Firefox cookies: {str(e)}")
            return None

    def _get_browser_cookies(self) -> Optional[str]:
        """Get cookies from installed browsers.
        
        Returns:
            Path to cookie file if successful, None otherwise
        """
        import browser_cookie3
        
        print("\nAttempting to load cookies from browsers...")
        
        # Define browser order based on preferred browser
        preferred = self.settings['cookies']['preferred_browser']
        print(f"Preferred browser: {preferred}")
        
        # Special handling for Firefox - try to find the cookie file directly first
        if preferred == 'firefox':
            print("Attempting to find Firefox cookie file directly...")
            firefox_cookie_file = self._find_firefox_cookie_file()
            if firefox_cookie_file:
                print("Converting Firefox cookies to Netscape format...")
                netscape_cookie_file = self._convert_firefox_cookies_to_netscape(firefox_cookie_file)
                if netscape_cookie_file:
                    print(f"Successfully converted Firefox cookies")
                    return netscape_cookie_file
                print("Failed to convert Firefox cookies, falling back to browser_cookie3...")
            else:
                print("Could not find Firefox cookie file directly, falling back to browser_cookie3...")
        
        browsers = {
            'chrome': browser_cookie3.chrome,
            'firefox': browser_cookie3.firefox,
            'edge': browser_cookie3.edge
        }
        
        # Try preferred browser first
        if preferred in browsers:
            try:
                print(f"\nTrying preferred browser ({preferred})...")
                cookies = browsers[preferred](domain_name='.youtube.com')
                cookie_count = sum(1 for _ in cookies)
                print(f"Found {cookie_count} cookies in {preferred}")
                
                if cookie_count > 0:
                    cookie_file = self._save_cookies_to_file(cookies)
                    if cookie_file:
                        print(f"Successfully saved {cookie_count} cookies from {preferred}")
                        return cookie_file
                    print(f"Failed to save cookies from {preferred}")
            except Exception as e:
                if "could not find" in str(e):
                    print(f"No {preferred} installation found")
                else:
                    print(f"Error accessing {preferred} cookies: {str(e)}")
        
        # Try other browsers if preferred browser failed
        other_browsers = {k: v for k, v in browsers.items() if k != preferred}
        for browser_name, browser_func in other_browsers.items():
            try:
                print(f"\nTrying fallback browser ({browser_name})...")
                cookies = browser_func(domain_name='.youtube.com')
                cookie_count = sum(1 for _ in cookies)
                print(f"Found {cookie_count} cookies in {browser_name}")
                
                if cookie_count > 0:
                    cookie_file = self._save_cookies_to_file(cookies)
                    if cookie_file:
                        print(f"Successfully saved {cookie_count} cookies from {browser_name}")
                        return cookie_file
                    print(f"Failed to save cookies from {browser_name}")
                else:
                    print(f"No YouTube cookies found in {browser_name}")
            except Exception as e:
                if "could not find" in str(e):
                    print(f"No {browser_name} installation found")
                else:
                    print(f"Error accessing {browser_name} cookies: {str(e)}")
        
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
        print("\nCookie configuration:")
        print(f"- Use browser cookies: {self.settings['cookies']['use_browser_cookies']}")
        print(f"- Custom cookies file: {self.settings['cookies']['custom_cookies_file']}")
        
        # Check if custom cookies file is specified
        if self.settings['cookies']['custom_cookies_file']:
            cookie_path = os.path.expanduser(self.settings['cookies']['custom_cookies_file'])
            print(f"\nChecking custom cookie file path: {cookie_path}")
            if os.path.exists(cookie_path):
                print(f"Using custom cookies file: {cookie_path}")
                return cookie_path, False
            else:
                print(f"Warning: Custom cookies file not found at {cookie_path}")
        
        # Fall back to browser cookies if enabled
        if self.settings['cookies']['use_browser_cookies']:
            print("\nAttempting to load cookies from browsers...")
            cookie_file = self._get_browser_cookies()
            if cookie_file:
                print(f"Using temporary cookie file: {cookie_file}")
            return cookie_file, bool(cookie_file and cookie_file.startswith(tempfile.gettempdir()))
        
        print("\nNo valid cookie source configured. Some videos might be unavailable.")
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
            
            # First check available formats
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("Checking video availability...")
                info = ydl.extract_info(url, download=False)
                print(f"Video found: {info.get('title', 'Unknown title')}")
                
                # Check available formats
                formats = info.get('formats', [])
                best_format = None
                best_format_id = None
                
                for f in formats:
                    if f.get('vcodec') == 'none':  # Audio only format
                        acodec = f.get('acodec', '').lower()
                        ext = f.get('ext', '').lower()
                        # Check both codec and extension since some opus streams are in webm containers
                        if acodec == 'opus' or ext == 'opus':
                            print(f"Found opus audio format (format_id: {f.get('format_id')}) - perfect match!")
                            best_format = f
                            best_format_id = f.get('format_id')
                            break
                        elif not best_format and acodec in ['m4a', 'mp4a', 'aac']:
                            best_format = f
                            best_format_id = f.get('format_id')
                
                if best_format:
                    if best_format.get('acodec', '').lower() == 'opus' or best_format.get('ext', '').lower() == 'opus':
                        print("Will download opus directly - no conversion needed")
                        ydl_opts.update({
                            'format': best_format_id,
                            'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                            'quiet': not self.settings['show_progress'],
                            'retries': 10,
                            'fragment_retries': 10,
                            'skip_unavailable_fragments': False,
                            'ignoreerrors': False
                        })
                    else:
                        print(f"Found audio-only format ({best_format.get('acodec')}) - will convert to opus")
                        ydl_opts.update({
                            'format': best_format_id,
                            'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                            'quiet': not self.settings['show_progress'],
                            'retries': 10,
                            'fragment_retries': 10,
                            'skip_unavailable_fragments': False,
                            'ignoreerrors': False
                        })
                else:
                    print("No audio-only format available - will extract audio from video")
                    ydl_opts.update({
                        'format': 'bestaudio/best',
                        'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                        'quiet': not self.settings['show_progress'],
                        'retries': 10,
                        'fragment_retries': 10,
                        'skip_unavailable_fragments': False,
                        'ignoreerrors': False
                    })
            
            # Now download with the selected format
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("\nStarting download...")
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
                # Check if we need to convert - only if it's not already opus audio
                need_conversion = True
                
                # If it's a webm file, check if it contains opus audio
                if downloaded_file.endswith('.webm'):
                    import subprocess
                    try:
                        # Use ffprobe to check the audio codec
                        result = subprocess.run([
                            'ffprobe',
                            '-v', 'error',
                            '-select_streams', 'a:0',
                            '-show_entries', 'stream=codec_name',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            downloaded_file
                        ], capture_output=True, text=True, check=True)
                        
                        if 'opus' in result.stdout.lower():
                            print("\nFile is already in opus format, just renaming to .opus extension")
                            need_conversion = False
                            # Rename the file to have .opus extension
                            output_file = os.path.splitext(downloaded_file)[0] + '.opus'
                            os.rename(downloaded_file, output_file)
                    except subprocess.CalledProcessError as e:
                        print(f"Warning: Could not check audio codec: {e.stderr}")
                        # If we can't check, assume we need to convert
                        need_conversion = True
                
                # If the downloaded file is not already in opus format and needs conversion
                if not downloaded_file.endswith('.opus') and need_conversion:
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
                            '-y',  # Add -y flag to automatically overwrite
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