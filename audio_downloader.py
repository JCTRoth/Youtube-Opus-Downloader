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
import time
import random
import tempfile
import sqlite3
import shutil
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
        self._temp_cookie_file = None  # Track temporary cookie files for cleanup
    
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
        """Get a random modern user agent string to avoid bot detection."""
        user_agents = [
            # Chrome on Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            # Chrome on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            # Firefox on Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
            # Firefox on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0',
            # Safari on macOS
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
            # Chrome on Linux
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ]
        return random.choice(user_agents)

    def _get_base_options(self, use_fallback_cookies: bool = False) -> Dict[str, Any]:
        """Get base options for yt-dlp with modern settings.
        
        Args:
            use_fallback_cookies: Whether to use fallback cookie methods
        
        Returns:
            Dictionary of yt-dlp options
        """
        options = {
            'quiet': not self.settings.get('show_progress', True),
            'no_warnings': not self.settings.get('show_progress', True),
        }
        
        # Handle custom cookie file if specified
        if not self.settings['cookies']['use_browser_cookies'] and self.settings['cookies']['custom_cookies_file']:
            print(f"\nUsing custom cookie file: {self.settings['cookies']['custom_cookies_file']}")
            options['cookiefile'] = self.settings['cookies']['custom_cookies_file']
        elif self.settings['cookies']['use_browser_cookies']:
            # For Firefox, always use the advanced cookie extraction as primary method
            # since yt-dlp's built-in cookiesfrombrowser doesn't work reliably with Firefox
            if self.settings['cookies']['preferred_browser'] == 'firefox' or use_fallback_cookies:
                # Use advanced cookie extraction as primary method for Firefox
                advanced_cookie_file = self._get_browser_cookies_fallback()
                if advanced_cookie_file:
                    options['cookiefile'] = advanced_cookie_file
                    self._temp_cookie_file = advanced_cookie_file  # Store for cleanup
                else:
                    print("\nAdvanced cookie extraction failed")
                    # Only fallback to built-in method for non-Firefox browsers
                    if self.settings['cookies']['preferred_browser'] != 'firefox':
                        print(f"Falling back to yt-dlp built-in cookie extraction for {self.settings['cookies']['preferred_browser']}")
                        options['cookiesfrombrowser'] = (self.settings['cookies']['preferred_browser'], None, None, None)
            else:
                # Use yt-dlp's built-in browser cookie extraction for Chrome/Edge
                print(f"\nUsing cookies from browser: {self.settings['cookies']['preferred_browser']}")
                options['cookiesfrombrowser'] = (self.settings['cookies']['preferred_browser'], None, None, None)
        else:
            print("\nNo cookies configured")
        
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

    def _save_cookies_to_file(self, cookies) -> Optional[str]:
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

    def _get_browser_cookies_fallback(self) -> Optional[str]:
        """Get cookies from installed browsers using browser_cookie3 as fallback.
        
        Returns:
            Path to cookie file if successful, None otherwise
        """
        try:
            import browser_cookie3
        except ImportError:
            print("Warning: browser_cookie3 not installed. Install with: pip install browser-cookie3")
            return None
        
        print("\nUsing advanced cookie extraction method...")
        
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
        
        print("\nWarning: Could not load cookies from any browser using advanced method.")
        print("\nMake sure you have at least one of these browsers installed and are logged into YouTube:")
        print("- Chrome")
        print("- Firefox")
        print("- Edge")
        return None

    def list_formats(self, url: str) -> Optional[List[Dict[str, Any]]]:
        """List all available formats for a video.
        
        Args:
            url: YouTube video URL
            
        Returns:
            List of format dictionaries if successful, None otherwise
        """
        ydl_opts = self._get_base_options()
        
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
                        filesize = f.get('filesize')
                        if filesize and isinstance(filesize, (int, float)):
                            filesize = f"{filesize/1024/1024:.1f}MB"
                        else:
                            filesize = "N/A"
                        note = f.get('format_note', '')
                        print(f"{format_id:11} {ext:9} {quality:16} {filesize:10} {note}")
                
                # Then print video formats
                if video_formats:
                    print("\nVideo formats (with audio if available):")
                    for format_id, ext, quality, f in video_formats:
                        filesize = f.get('filesize')
                        if filesize and isinstance(filesize, (int, float)):
                            filesize = f"{filesize/1024/1024:.1f}MB"
                        else:
                            filesize = "N/A"
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
        
        try:
            # If --list-formats is specified, just list formats and exit
            if '--list-formats' in sys.argv:
                self.list_formats(url)
                return
            
            # Get base options and add download-specific options
            ydl_opts = self._get_base_options()
            
            # Configure for audio extraction
            ydl_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                'quiet': not self.settings['show_progress'],
                'no_warnings': not self.settings['show_progress'],
                'extractaudio': True,
                'audioformat': self.settings['audio_format'],
                'audioquality': self.settings['audio_quality'],
                'prefer_ffmpeg': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.settings['audio_format'],
                    'preferredquality': self.settings['audio_quality'],
                }],
                'retries': 10,
                'fragment_retries': 10,
                'skip_unavailable_fragments': False,
                'ignoreerrors': False,
                'sleep_interval': 1,  # Add sleep between downloads to be respectful
                'max_sleep_interval': 5,
            })
            
            # Download and extract audio
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("Checking video availability...")
                info = ydl.extract_info(url, download=False)
                print(f"Video found: {info.get('title', 'Unknown title')}")
                print(f"Duration: {info.get('duration', 'Unknown')} seconds")
                
                print("\nStarting download...")
                ydl.download([url])
                
                print(f"\nDownload completed! File saved in: {self.settings['download_directory']}")
                
        except yt_dlp.DownloadError as e:
            error_str = str(e)
            print(f"\nDownload error: {error_str}")
            
            # Try advanced cookie method if the error might be cookie-related
            if any(keyword in error_str.lower() for keyword in ['cookies', 'login', 'sign in', 'private', 'unavailable']):
                print("\nAttempting download with advanced cookie extraction...")
                try:
                    # Retry with advanced cookies
                    ydl_opts_advanced = self._get_base_options(use_fallback_cookies=True)
                    ydl_opts_advanced.update({
                        'format': 'bestaudio/best',
                        'outtmpl': os.path.join(self.settings['download_directory'], '%(title)s.%(ext)s'),
                        'quiet': not self.settings['show_progress'],
                        'no_warnings': not self.settings['show_progress'],
                        'extractaudio': True,
                        'audioformat': self.settings['audio_format'],
                        'audioquality': self.settings['audio_quality'],
                        'prefer_ffmpeg': True,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': self.settings['audio_format'],
                            'preferredquality': self.settings['audio_quality'],
                        }],
                        'retries': 10,
                        'fragment_retries': 10,
                        'skip_unavailable_fragments': False,
                        'ignoreerrors': False,
                        'sleep_interval': 1,
                        'max_sleep_interval': 5,
                    })
                    
                    with yt_dlp.YoutubeDL(ydl_opts_advanced) as ydl:
                        print("Retrying download with advanced cookies...")
                        ydl.download([url])
                        print(f"\nDownload completed with advanced method! File saved in: {self.settings['download_directory']}")
                        return  # Success with advanced method
                        
                except Exception as advanced_e:
                    print(f"Advanced method also failed: {str(advanced_e)}")
            
            print("This may be due to:")
            print("- Video unavailable or private")
            print("- Geographic restrictions")
            print("- Network connection issues")
            print("\nTry:")
            print("1. Check if the video is accessible in your browser")
            print("2. Update yt-dlp to the latest version")
            print("3. Try again later")
            
        except Exception as e:
            print(f"\nUnexpected error: {str(e)}")
            print("Please check your settings and try again.")
            if "HTTP Error 403" in str(e):
                print("\nTip: YouTube blocked the request. Try:")
                print("1. Waiting a few minutes before trying again")
                print("2. Using a different browser's cookies")
                print("3. Opening the video in your browser first")
                
        finally:
            # Clean up temporary cookie file if created
            if hasattr(self, '_temp_cookie_file') and self._temp_cookie_file and os.path.exists(self._temp_cookie_file):
                try:
                    os.unlink(self._temp_cookie_file)
                    self._temp_cookie_file = None
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