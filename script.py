!pip install -q requests-toolbelt

# API_URL = "https://zzlgmmtn-3000.inc1.devtunnels.ms"

# !apt-get update

# !apt-get install -y \
# git \
# cmake \
# build-essential \
# gperf \
# zlib1g-dev \
# libssl-dev \
# libreadline-dev \
# pkg-config

# !pwd
# !ls -la

# import os

# os.chdir("/content")
# print(os.getcwd())

# !rm -rf /content/telegram-bot-api

# !git clone --recursive https://github.com/tdlib/telegram-bot-api.git

# %cd /content/telegram-bot-api

# !mkdir build
# %cd build

# !cmake -DCMAKE_BUILD_TYPE=Release ..
# !make -j$(nproc)



print("ok")

# # from google.colab import drive
# # drive.mount('/content/drive')


# import gdown
# from google.oauth2 import service_account
# from googleapiclient.discovery import build

# # 1. Define the file ID from your public Drive link
# file_id = '1qFs17BIQYPV5SOTHmcHByxeN86vCrxkP'
# drive_url = f'https://drive.google.com/uc?id={file_id}'
# KEY_FILE = '/content/service_account.json'

# # 2. Download the JSON file directly into the Colab environment
# print("Downloading service account credentials...")
# gdown.download(drive_url, KEY_FILE, quiet=False)

# # 3. Authenticate silently using the freshly downloaded key
# print("Authenticating...")
# credentials = service_account.Credentials.from_service_account_file(
#     KEY_FILE,
#     scopes=["https://www.googleapis.com/auth/drive.readonly"]
# )

# # 4. Initialize the Drive API service
# drive_service = build('drive', 'v3', credentials=credentials)
# print("✅ Successfully authenticated via service account!")

# import os
# import io
# import json
# import shutil
# import mimetypes
# from datetime import datetime, timezone

# import gdown
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# # ---------------------------------------------------------
# # CONFIGURATION (Uses relative paths for clean remote setups)
# # ---------------------------------------------------------
# BASE_DIR = os.getcwd()
# CREDENTIALS_FILE_ID = '1qFs17BIQYPV5SOTHmcHByxeN86vCrxkP'
# drive_url = f'https://drive.google.com/uc?id={CREDENTIALS_FILE_ID}'
# KEY_FILE = os.path.join(BASE_DIR, 'service_account.json')

# TARGET_DATA_FOLDER_ID = '1mVKnRvEvmu-CjPxEczzR9NFxC7mBFa1Q'
# folder_ids = [
#     TARGET_DATA_FOLDER_ID,
#     '1HYsxfBaROs8XUaUQzsLy1J-ox1jZkxB5'
# ]

# DOWNLOAD_BASE = os.path.join(BASE_DIR, "downloads")
# DRIVE_DIR = os.path.join(DOWNLOAD_BASE, TARGET_DATA_FOLDER_ID)

# # ---------------------------------------------------------
# # 1. AUTHENTICATION (Full Drive Read/Write Access)
# # ---------------------------------------------------------
# print("Downloading service account credentials...")
# # Added quiet=True to keep output clear when executed remotely via orchestrator
# gdown.download(drive_url, KEY_FILE, quiet=True)

# print("Authenticating with Google Drive API...")
# credentials = service_account.Credentials.from_service_account_file(
#     KEY_FILE,
#     scopes=["https://www.googleapis.com/auth/drive"]
# )

# drive_service = build('drive', 'v3', credentials=credentials)
# print("✅ Successfully authenticated via service account!")

# # ---------------------------------------------------------
# # 2. DRIVE UPLOAD & SYNC FUNCTIONS
# # ---------------------------------------------------------
# def upload_or_update_file_to_drive(service, local_file_path: str, folder_id: str) -> None:
#     """Uploads a local file to Google Drive (overwrites if it exists, creates if new)."""
#     if not os.path.exists(local_file_path):
#         print(f"⚠️ Cannot upload: Local file '{local_file_path}' does not exist.")
#         return

#     file_name = os.path.basename(local_file_path)

#     # FIX: Single quotes must be escaped as two single quotes in Drive API queries, not backslashes.
#     safe_file_name = file_name.replace("'", "''")
#     query = f"'{folder_id}' in parents and name = '{safe_file_name}' and trashed = false"

#     results = service.files().list(q=query, fields="files(id, name)").execute()
#     items = results.get('files', [])

#     mime_type, _ = mimetypes.guess_type(local_file_path)
#     if mime_type is None:
#         mime_type = 'application/json'

#     media = MediaFileUpload(local_file_path, mimetype=mime_type, resumable=True)

#     if items:
#         # File exists -> Update existing file
#         existing_file_id = items[0]['id']
#         service.files().update(
#             fileId=existing_file_id,
#             media_body=media,
#             fields='id'
#         ).execute()
#         print(f"☁️ ✅ Updated existing '{file_name}' on Google Drive (ID: {existing_file_id})")
#     else:
#         # File does not exist -> Create new file inside target folder
#         file_metadata = {
#             'name': file_name,
#             'parents': [folder_id]
#         }
#         created_file = service.files().create(
#             body=file_metadata,
#             media_body=media,
#             fields='id'
#         ).execute()
#         print(f"☁️ ✅ Created new '{file_name}' on Google Drive (ID: {created_file.get('id')})")


# # ---------------------------------------------------------
# # 3. DOWNLOAD FOLDER CONTENTS
# # ---------------------------------------------------------
# def download_folder_contents(service, folder_id, destination_path):
#     os.makedirs(destination_path, exist_ok=True)

#     query = f"'{folder_id}' in parents and trashed = false"
#     results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
#     items = results.get('files', [])

#     if not items:
#         print(f"⚠️ Folder {folder_id} is empty or not shared with the service account.")
#     else:
#         for item in items:
#             if item['mimeType'] == 'application/vnd.google-apps.folder':
#                 print(f"📁 Skipping subfolder: {item['name']}")
#                 continue

#             print(f"📥 Downloading: {item['name']}...")
#             request = service.files().get_media(fileId=item['id'])
#             file_path = os.path.join(destination_path, item['name'])

#             with io.FileIO(file_path, 'wb') as f:
#                 downloader = MediaIoBaseDownload(f, request)
#                 done = False
#                 while not done:
#                     status, done = downloader.next_chunk()
#             print(f"✅ Saved to {file_path}")

# # ---------------------------------------------------------
# # 4. EXECUTION
# # ---------------------------------------------------------
# for fid in folder_ids:
#     print(f"\n----------------------------------------")
#     print(f"📦 Processing folder ID: {fid}")
#     print(f"----------------------------------------")
#     download_folder_contents(drive_service, fid, os.path.join(DOWNLOAD_BASE, fid))

# print("\n🎉 All folder download tasks completed!")

# # ---------------------------------------------------------
# # 5. POST-DOWNLOAD INTEGRATION
# # ---------------------------------------------------------
# # Fix: Ensure the current cache files are read dynamically from storage setup right away.

# BOT_API_SOURCE = os.path.join(DOWNLOAD_BASE, '1HYsxfBaROs8XUaUQzsLy1J-ox1jZkxB5', 'telegram-bot-api')
# BOT_API_DEST = os.path.join(BASE_DIR, 'telegram-bot-api')

# if os.path.exists(BOT_API_SOURCE):
#     shutil.copy2(BOT_API_SOURCE, BOT_API_DEST)
#     try:
#         os.chmod(BOT_API_DEST, 0o755)
#         print("✅ telegram-bot-api moved and made executable successfully!")
#     except Exception as e:
#         print(f"⚠️ Could not adjust permissions on this OS: {e}")
# else:
#     print("⚠️ telegram-bot-api not found in downloads path.")

import os
import io
import json
import shutil
import mimetypes
from datetime import datetime, timezone

import gdown
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ---------------------------------------------------------
# CONFIGURATION (Uses relative paths for clean remote setups)
# ---------------------------------------------------------
BASE_DIR = os.getcwd()
CREDENTIALS_FILE_ID = '1qFs17BIQYPV5SOTHmcHByxeN86vCrxkP'
drive_url = f'https://drive.google.com/uc?id={CREDENTIALS_FILE_ID}'
KEY_FILE = os.path.join(BASE_DIR, 'service_account.json')

TARGET_DATA_FOLDER_ID = '1mVKnRvEvmu-CjPxEczzR9NFxC7mBFa1Q'
folder_ids = [
    TARGET_DATA_FOLDER_ID,
    '1HYsxfBaROs8XUaUQzsLy1J-ox1jZkxB5'
]

DOWNLOAD_BASE = os.path.join(BASE_DIR, "downloads")

# ---------------------------------------------------------
# 1. AUTHENTICATION (Full Drive Read/Write Access)
# ---------------------------------------------------------
print("Downloading service account credentials...")
gdown.download(drive_url, KEY_FILE, quiet=True)

print("Authenticating with Google Drive API...")
credentials = service_account.Credentials.from_service_account_file(
    KEY_FILE,
    scopes=["https://www.googleapis.com/auth/drive"]
)

drive_service = build('drive', 'v3', credentials=credentials)
print("✅ Successfully authenticated via service account!")

# ---------------------------------------------------------
# 2. DOWNLOAD FOLDER CONTENTS
# ---------------------------------------------------------
def download_folder_contents(service, folder_id, destination_path):
    os.makedirs(destination_path, exist_ok=True)

    query = f"'{folder_id}' in parents and trashed = false"

    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    items = results.get('files', [])

    if not items:
        print(f"⚠️ Folder {folder_id} is empty or not shared with the service account.")
    else:
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                print(f"📁 Skipping subfolder: {item['name']}")
                continue

            print(f"📥 Downloading: {item['name']}...")
            request = service.files().get_media(fileId=item['id'])
            file_path = os.path.join(destination_path, item['name'])

            with io.FileIO(file_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            print(f"✅ Saved to {file_path}")

# ---------------------------------------------------------
# 3. EXECUTION
# ---------------------------------------------------------
for fid in folder_ids:
    print(f"\n----------------------------------------")
    print(f"📦 Processing folder ID: {fid}")
    print(f"----------------------------------------")
    download_folder_contents(drive_service, fid, os.path.join(DOWNLOAD_BASE, fid))

print("\n🎉 All folder download tasks completed!")

# ---------------------------------------------------------
# 4. POST-DOWNLOAD TELEGRAM BOT INTEGRATION
# ---------------------------------------------------------
BOT_API_SOURCE = os.path.join(DOWNLOAD_BASE, '1HYsxfBaROs8XUaUQzsLy1J-ox1jZkxB5', 'telegram-bot-api')
BOT_API_DEST = os.path.join(BASE_DIR, 'telegram-bot-api')

if os.path.exists(BOT_API_SOURCE):
    shutil.copy2(BOT_API_SOURCE, BOT_API_DEST)
    try:
        os.chmod(BOT_API_DEST, 0o755)
        print("✅ telegram-bot-api moved and made executable successfully!")
    except Exception as e:
        print(f"⚠️ Could not adjust permissions on this OS: {e}")
else:
    print("⚠️ telegram-bot-api not found in downloads path.")

# !find /content/telegram-bot-api -type f -name telegram-bot-api

# !mkdir -p "/content/drive/MyDrive/TelegramBotAPI"

# !cp /content/telegram-bot-api/build/telegram-bot-api \
# "/content/drive/MyDrive/TelegramBotAPI/"

# !ls -lh "/content/drive/MyDrive/TelegramBotAPI/"

# !chmod +x "/content/drive/MyDrive/TelegramBotAPI/telegram-bot-api"

# !"/content/drive/MyDrive/TelegramBotAPI/telegram-bot-api" --help

# !cp "/content/drive/MyDrive/TelegramBotAPI/telegram-bot-api" /content/
# !chmod +x /content/telegram-bot-api

import os

os.chdir("/content")
print(os.getcwd())

!nohup /content/telegram-bot-api \
  --api-id=22219997 \
  --api-hash=e3840aec1ee4daefa979d3ceeecba323 \
  --local \
  --http-port=8081 \
  > telegram.log 2>&1 &

!ps -ef | grep telegram-bot-api

# !killall telegram-bot-api

!curl "http://127.0.0.1:8081/bot8686715928:AAHduhKLmirJokgi8mXYA46fjZUfRobG7a4/getMe"

!pip install -q pyrogram tgcrypto requests colorama tqdm
!apt-get -y -qq install ffmpeg

# # ====== TELEGRAM CONFIG ======
# API_ID = 22219997                     # from https://my.telegram.org
# API_HASH = "e3840aec1ee4daefa979d3ceeecba323"
# BOT_TOKEN = "7585583046:AAESix1g0gpKbpCsF-XFQcb0fTzvSfoXW2o"
# CHAT_ID = "-1003349292789"  # or numeric chat id, e.g. main  -1003349292789  file -1003795957493

# DOWNLOAD_DIR = "/content/downloads"
# CHUNK_SIZE = 1024 * 1024   # 1 MB
# MAX_RETRIES = 5

# import os
# os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# API_ID = 22219997                     # from https://my.telegram.org
# API_HASH = "e3840aec1ee4daefa979d3ceeecba323"
# BOT_TOKEN = "7585583046:AAESix1g0gpKbpCsF-XFQcb0fTzvSfoXW2o"
# CHAT_ID = "-1003349292789"  # or numeric chat id, e.g. -1001234567890

# import subprocess, time

# # # Start the local bot API server in the background
# # server_proc = subprocess.Popen(
# #     [
# #         "/content/telegram-bot-api",
# #         f"--api-id={API_ID}",
# #         f"--api-hash={API_HASH}",
# #         "--local",
# #         "--http-port=8081"
# #     ],
# #     stdout=subprocess.DEVNULL,
# #     stderr=subprocess.DEVNULL
# # )
# # time.sleep(5)
# # print("Local Bot API server started, PID:", server_proc.pid)

# BOT_API = f"http://127.0.0.1:8081/bot{BOT_TOKEN}"

# import os, sys, time, json, subprocess, requests
# from datetime import datetime
# from colorama import Fore, Style, init as colorama_init
# colorama_init(autoreset=True)

# DOWNLOAD_DIR = "/content/downloads"
# os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# MAX_RETRIES = 5

# def log_info(msg): print(Fore.CYAN + "[INFO] " + Style.RESET_ALL + msg)
# def log_success(msg): print(Fore.GREEN + "[OK] " + Style.RESET_ALL + msg)
# def log_warn(msg): print(Fore.YELLOW + "[WARN] " + Style.RESET_ALL + msg)
# def log_error(msg): print(Fore.RED + "[ERROR] " + Style.RESET_ALL + msg)

# def human_size(n):
#     for unit in ["B","KB","MB","GB","TB"]:
#         if n < 1024:
#             return f"{n:.2f} {unit}"
#         n /= 1024
#     return f"{n:.2f} PB"

# def format_duration(seconds):
#     h = seconds // 3600
#     m = (seconds % 3600) // 60
#     s = seconds % 60
#     return f"{h:02d}:{m:02d}:{s:02d}"

# import re
# import os
# import time
# from urllib.parse import urlparse, unquote
# import mimetypes
# import requests
# from colorama import Fore, Style

# def clean_filename(filename):
#     name, ext = os.path.splitext(filename)

#     # Replace dots with spaces
#     name = name.replace(".", " ")
#     name = " ".join(name.split())  # collapse multiple spaces

#     # Remove site-tag prefix like "Movies4u Foo" (case-insensitive, with optional separators)
#     name = re.sub(r"^Movies4u[\s_.-]*Foo[\s_.-]*", "", name, flags=re.IGNORECASE)

#     # Remove any other bracketed junk at the start, e.g. [Movies4u.foo]
#     name = re.sub(r"^\[.*?\]\s*", "", name, flags=re.IGNORECASE)

#     return name.strip() + ext   # <-- FIXED: extension is now preserved


# def get_filename_from_headers(url):
#     """Try to determine the real filename from HTTP headers."""
#     try:
#         # Try HEAD first (fast, no body download)
#         r = requests.head(url, allow_redirects=True, timeout=15)
#         headers = r.headers

#         # Some servers don't support HEAD properly (405/501) — fallback to GET with stream
#         if r.status_code >= 400 or "content-disposition" not in {k.lower() for k in headers.keys()}:
#             r2 = requests.get(url, stream=True, timeout=15)
#             headers = r2.headers
#             r2.close()
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Could not fetch headers ({e}), will fall back to URL/random name.")
#         headers = {}

#     filename = None

#     # 1. Content-Disposition header (most reliable)
#     cd = headers.get("Content-Disposition") or headers.get("content-disposition")
#     if cd:
#         # handles: filename="movie.mkv"  or  filename*=UTF-8''movie.mkv
#         match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
#         if not match:
#             match = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
#         if match:
#             filename = unquote(match.group(1).strip())

#     # 2. Fallback: last segment of the URL path (if it looks like a real filename)
#     if not filename:
#         path = urlparse(url).path
#         candidate = os.path.basename(path)
#         if candidate and "." in candidate:
#             filename = unquote(candidate)

#     # 3. Fallback: generate a name + guess extension from Content-Type
#     if not filename:
#         content_type = headers.get("Content-Type", "").split(";")[0].strip()
#         ext = mimetypes.guess_extension(content_type) or ".mp4"
#         filename = f"video_{int(time.time())}{ext}"

#     # Sanitize filename (remove illegal filesystem characters)
#     filename = re.sub(r'[\\/*?:"<>|]', "_", filename)

#     # Clean up (dots → spaces, strip junk prefix) — extension preserved
#     filename = clean_filename(filename)

#     # Safety net: if for any reason the extension got lost, default to .mp4
#     if not os.path.splitext(filename)[1]:
#         filename += ".mp4"
#         log_warn(f"No extension detected — defaulted to: {filename}")

#     log_info(f"Detected filename: {filename}")
#     return filename


# def download_file(url, dest_path):
#     for attempt in range(1, MAX_RETRIES + 1):
#         try:
#             resume_byte_pos = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
#             headers = {"Range": f"bytes={resume_byte_pos}-"} if resume_byte_pos else {}
#             if resume_byte_pos:
#                 log_warn(f"Resuming from {human_size(resume_byte_pos)}")

#             with requests.get(url, headers=headers, stream=True, timeout=30) as r:
#                 r.raise_for_status()
#                 total_size = int(r.headers.get("content-length", 0)) + resume_byte_pos
#                 mode = "ab" if resume_byte_pos else "wb"
#                 downloaded = resume_byte_pos
#                 start_time = time.time()

#                 with open(dest_path, mode) as f:
#                     for chunk in r.iter_content(chunk_size=1024*1024):
#                         if not chunk:
#                             continue
#                         f.write(chunk)
#                         downloaded += len(chunk)
#                         elapsed = time.time() - start_time
#                         speed = (downloaded - resume_byte_pos) / elapsed if elapsed > 0 else 0
#                         percent = (downloaded / total_size * 100) if total_size else 0
#                         eta = (total_size - downloaded) / speed if speed > 0 else 0
#                         bar_len = 30
#                         filled = int(bar_len * percent / 100)
#                         bar = "█"*filled + "-"*(bar_len-filled)
#                         sys.stdout.write(
#                             f"\r{Fore.BLUE}⬇ Downloading{Style.RESET_ALL} [{bar}] "
#                             f"{percent:5.1f}% | {human_size(downloaded)}/{human_size(total_size)} "
#                             f"| {human_size(speed)}/s | ETA: {int(eta)}s   "
#                         )
#                         sys.stdout.flush()
#                 print()
#                 log_success(f"Download complete: {dest_path}")
#                 return True
#         except (requests.exceptions.RequestException, ConnectionError) as e:
#             log_error(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
#             time.sleep(3 * attempt)
#     log_error("All download attempts failed.")
#     return False

# def get_video_metadata(path):
#     cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     data = json.loads(result.stdout)
#     video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
#     duration = float(data.get("format", {}).get("duration", 0))
#     width = int(video_stream.get("width", 0)) if video_stream else 0
#     height = int(video_stream.get("height", 0)) if video_stream else 0
#     size = int(data.get("format", {}).get("size", os.path.getsize(path)))
#     return {"duration": int(duration), "width": width, "height": height, "size": size}

# # Cell — Download poster image instead of generating a thumbnail from the video

# def download_poster_thumbnail(poster_url: str, video_path: str, timeout: int = 20) -> str | None:
#     """
#     Downloads the poster image from the API's poster_url and saves it
#     alongside the video as the thumbnail, instead of generating one via ffmpeg.
#     Returns the local thumb path, or None on failure.
#     """
#     if not poster_url:
#         log_warn("No poster_url provided — skipping thumbnail.")
#         return None

#     thumb_path = video_path + "_thumb.jpg"

#     try:
#         resp = requests.get(poster_url, timeout=timeout, stream=True)
#         resp.raise_for_status()

#         with open(thumb_path, "wb") as f:
#             for chunk in resp.iter_content(chunk_size=8192):
#                 f.write(chunk)

#         log_success(f"Poster thumbnail downloaded: {thumb_path}")
#         return thumb_path

#     except requests.exceptions.RequestException as e:
#         log_warn(f"Poster download failed: {e}")
#         return None

# # Cell — Detect actual video mimetype from the file (no conversion)

# import mimetypes

# def get_video_mimetype(file_path: str) -> str:
#     """
#     Detects the real mimetype based on file extension.
#     No conversion — just reports what the file actually is.
#     """
#     mime_map = {
#         ".mp4": "video/mp4",
#         ".mkv": "video/x-matroska",
#         ".webm": "video/webm",
#         ".mov": "video/quicktime",
#         ".avi": "video/x-msvideo",
#         ".ts": "video/mp2t",
#         ".m4v": "video/x-m4v",
#     }

#     ext = os.path.splitext(file_path)[1].lower()
#     if ext in mime_map:
#         return mime_map[ext]

#     # Fallback: let Python's mimetypes module guess
#     guessed, _ = mimetypes.guess_type(file_path)
#     if guessed:
#         return guessed

#     log_warn(f"Could not determine mimetype for {file_path}, defaulting to video/mp4")
#     return "video/mp4"

# def upload_video(file_path, thumb_path, caption, duration, width, height, display_filename=None):
#     file_size = os.path.getsize(file_path)
#     start_time = time.time()
#     last_print = [0]

#     video_mime = get_video_mimetype(file_path)
#     upload_name = display_filename or os.path.basename(file_path)
#     log_info(f"Uploading '{upload_name}' with mimetype: {video_mime}")

#     def create_callback(monitor):
#         def callback(m):
#             now = time.time()
#             if now - last_print[0] < 0.3 and m.bytes_read != m.len:
#                 return
#             last_print[0] = now
#             percent = m.bytes_read / m.len * 100
#             elapsed = now - start_time
#             speed = m.bytes_read / elapsed if elapsed > 0 else 0
#             eta = (m.len - m.bytes_read) / speed if speed > 0 else 0
#             bar_len = 30
#             filled = int(bar_len * percent / 100)
#             bar = "█"*filled + "-"*(bar_len-filled)
#             sys.stdout.write(
#                 f"\r{Fore.MAGENTA}⬆ Uploading{Style.RESET_ALL} [{bar}] "
#                 f"{percent:5.1f}% | {human_size(m.bytes_read)}/{human_size(m.len)} "
#                 f"| {human_size(speed)}/s | ETA: {int(eta)}s   "
#             )
#             sys.stdout.flush()
#         return callback

#     fields = {
#         "chat_id": CHAT_ID,
#         "caption": caption,
#         "duration": str(duration),
#         "width": str(width),
#         "height": str(height),
#         "supports_streaming": "true",
#         "video": (upload_name, open(file_path, "rb"), video_mime),
#     }
#     if thumb_path and os.path.exists(thumb_path):
#         fields["thumb"] = (os.path.basename(thumb_path), open(thumb_path, "rb"), "image/jpeg")

#     encoder = MultipartEncoder(fields=fields)
#     monitor = MultipartEncoderMonitor(encoder, create_callback(encoder))

#     try:
#         response = requests.post(
#             f"{BOT_API}/sendVideo",
#             data=monitor,
#             headers={"Content-Type": monitor.content_type},
#             timeout=None
#         )
#         print()
#         result = response.json()
#         if result.get("ok"):
#             log_success(f"Upload verified — message_id: {result['result']['message_id']}")
#             return True
#         else:
#             log_error(f"Upload failed: {result}")
#             return False
#     except Exception as e:
#         print()
#         log_error(f"Upload exception: {e}")
#         return False

# # Cell — Extended: size check + zip-file skip

# MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB limit

# SKIP_EXTENSIONS = {".zip", ".rar", ".7z"}  # add more archive types here if needed
# SKIP_CONTENT_TYPES = {
#     "application/zip",
#     "application/x-zip-compressed",
#     "application/x-rar-compressed",
#     "application/x-7z-compressed",
#     "application/octet-stream",  # NOTE: generic binary, sometimes used for zips too — see note below
# }


# def is_archive_file(url: str, filename: str, timeout: int = 15) -> tuple[bool, str]:
#     """
#     Checks whether a file is a zip/archive, via both filename extension and Content-Type header.
#     Returns (is_archive, reason).
#     """
#     # Check 1: filename extension (fast, no network call)
#     ext = os.path.splitext(filename)[1].lower()
#     if ext in SKIP_EXTENSIONS:
#         return True, f"extension '{ext}'"

#     # Check 2: Content-Type header (catches cases where URL/filename hides the real type)
#     try:
#         resp = requests.head(url, timeout=timeout, allow_redirects=True)
#         content_type = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
#         if content_type in {"application/zip", "application/x-zip-compressed",
#                              "application/x-rar-compressed", "application/x-7z-compressed"}:
#             return True, f"content-type '{content_type}'"
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Could not check content-type for archive detection: {e}")

#     return False, ""


# def get_remote_file_size(url: str, timeout: int = 15) -> int | None:
#     """Checks remote file size via headers without downloading the body."""
#     try:
#         resp = requests.head(url, timeout=timeout, allow_redirects=True)
#         size = resp.headers.get("Content-Length")
#         if size and size.isdigit():
#             return int(size)
#     except requests.exceptions.RequestException as e:
#         log_warn(f"HEAD request failed for size check: {e}")

#     try:
#         resp = requests.get(url, timeout=timeout, stream=True, headers={"Range": "bytes=0-0"})
#         content_range = resp.headers.get("Content-Range")
#         if content_range and "/" in content_range:
#             total = content_range.split("/")[-1]
#             if total.isdigit():
#                 return int(total)
#         content_length = resp.headers.get("Content-Length")
#         if content_length and content_length.isdigit():
#             return int(content_length)
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Ranged GET size check also failed: {e}")

#     return None


# def is_within_size_limit(url: str, max_bytes: int = MAX_SIZE_BYTES) -> tuple[bool, int | None]:
#     """Returns (is_ok, size_bytes). Fail-safe: unknown size = not ok."""
#     size = get_remote_file_size(url)
#     if size is None:
#         return False, None
#     return size < max_bytes, size

# # ============================================================
# # NEW: video preparation helpers (streaming-safe MP4 output)
# # ============================================================

# def probe_stream_info(path: str) -> dict:
#     """FFprobe-based inspection of container + codec details."""
#     cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
#            "-show_format", "-show_streams", path]
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     data = json.loads(result.stdout) if result.stdout else {}
#     fmt = data.get("format", {})
#     v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
#     a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
#     return {
#         "format_name": fmt.get("format_name", ""),
#         "video_codec": v.get("codec_name") if v else None,
#         "audio_codec": a.get("codec_name") if a else None,
#         "pix_fmt": v.get("pix_fmt") if v else None,
#         "width": int(v.get("width", 0)) if v else 0,
#         "height": int(v.get("height", 0)) if v else 0,
#         "duration": float(fmt.get("duration", 0) or 0),
#         "size": int(fmt.get("size", os.path.getsize(path))) if os.path.exists(path) else 0,
#     }


# def check_faststart(mp4_path: str):
#     """
#     Manually walks top-level MP4 atoms to confirm 'moov' appears before 'mdat'.
#     Returns True / False, or None if it can't be determined (e.g. non-MP4 input).
#     """
#     try:
#         filesize = os.path.getsize(mp4_path)
#         pos_moov, pos_mdat = None, None
#         with open(mp4_path, "rb") as f:
#             offset = 0
#             while offset < filesize:
#                 f.seek(offset)
#                 header = f.read(8)
#                 if len(header) < 8:
#                     break
#                 size = int.from_bytes(header[0:4], "big")
#                 atom_type = header[4:8].decode("ascii", errors="ignore")
#                 if atom_type == "moov" and pos_moov is None:
#                     pos_moov = offset
#                 if atom_type == "mdat" and pos_mdat is None:
#                     pos_mdat = offset
#                 if pos_moov is not None and pos_mdat is not None:
#                     break
#                 if size == 1:  # 64-bit extended size
#                     ext = f.read(8)
#                     if len(ext) < 8:
#                         break
#                     size = int.from_bytes(ext, "big")
#                 elif size == 0:
#                     break
#                 offset += size
#         if pos_moov is None or pos_mdat is None:
#             return None
#         return pos_moov < pos_mdat
#     except Exception as e:
#         log_warn(f"faststart check failed: {e}")
#         return None


# def run_ffmpeg(cmd: list, label: str) -> bool:
#     log_info(f"ffmpeg [{label}]: {' '.join(cmd)}")
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     if result.returncode != 0:
#         log_error(f"ffmpeg [{label}] failed:\n{result.stderr[-2000:]}")
#         return False
#     return True


# def prepare_video_for_telegram(src_path: str):
#     """
#     Decision tree:
#       1. Always try a lossless remux to MP4 + faststart first (-c copy).
#       2. If the remux is H.264 + AAC(-or-none)  -> done, no re-encode.
#       3. If the remux is H.264 + non-AAC audio  -> cheap audio-only AAC transcode
#          (video stream stays copied, not re-encoded).
#       4. If the remux is still non-H.264 video (HEVC/VP9/AV1/etc.) -> fall back
#          to a speed-oriented libx264 + AAC re-encode.
#     Returns (final_path, info_dict) or (None, None) on total failure.
#     Does NOT delete src_path — caller decides cleanup.
#     """
#     info = probe_stream_info(src_path)
#     base, _ = os.path.splitext(src_path)
#     remux_path = base + "_stream.mp4"
#     fallback_path = base + "_h264.mp4"

#     log_info(f"Source probe: container={info['format_name']} "
#               f"video={info['video_codec']} audio={info['audio_codec']} "
#               f"{info['width']}x{info['height']}")

#     # Step 1: cheap remux attempt (covers both "already compatible" and "MKV/HEVC" cases)
#     remux_cmd = [
#         "ffmpeg", "-y", "-i", src_path,
#         "-map", "0:v:0", "-map", "0:a:0?",
#         "-c", "copy", "-movflags", "+faststart",
#         remux_path
#     ]
#     remux_ok = run_ffmpeg(remux_cmd, "remux -c copy +faststart")

#     if remux_ok and os.path.exists(remux_path):
#         r_info = probe_stream_info(remux_path)

#         if r_info["video_codec"] == "h264":
#             if r_info["audio_codec"] in ("aac", None):
#                 log_success("Remux OK: H.264 (+AAC/none) — already streamable, no re-encode.")
#                 return remux_path, r_info

#             # Video fine, audio isn't AAC -> cheap audio-only fix, video stays copied
#             log_warn(f"Audio codec '{r_info['audio_codec']}' isn't AAC — "
#                       f"transcoding audio only.")
#             audio_fix_path = base + "_audiofix.mp4"
#             audio_cmd = [
#                 "ffmpeg", "-y", "-i", remux_path,
#                 "-map", "0:v:0", "-map", "0:a:0?",
#                 "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
#                 "-movflags", "+faststart",
#                 audio_fix_path
#             ]
#             if run_ffmpeg(audio_cmd, "audio-only AAC fix") and os.path.exists(audio_fix_path):
#                 try: os.remove(remux_path)
#                 except Exception: pass
#                 return audio_fix_path, probe_stream_info(audio_fix_path)
#             log_warn("Audio-only fix failed — falling through to full re-encode.")
#         else:
#             log_warn(f"Remux kept non-H.264 video ('{r_info['video_codec']}') — not "
#                       f"guaranteed to stream/seek reliably on all Telegram mobile "
#                       f"clients. Falling back to H.264 conversion.")

#         try: os.remove(remux_path)
#         except Exception: pass
#     else:
#         log_warn("Remux step failed/empty — proceeding straight to fallback conversion.")

#     # Step 2: fallback — speed-oriented H.264 + AAC re-encode
#     fallback_cmd = [
#         "ffmpeg", "-y", "-i", src_path,
#         "-map", "0:v:0", "-map", "0:a:0?",
#         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
#         "-pix_fmt", "yuv420p",
#         "-c:a", "aac", "-b:a", "128k",
#         "-movflags", "+faststart",
#         fallback_path
#     ]
#     if not run_ffmpeg(fallback_cmd, "fallback H.264/AAC re-encode") or not os.path.exists(fallback_path):
#         log_error("Fallback conversion failed — no streamable output could be produced.")
#         return None, None

#     f_info = probe_stream_info(fallback_path)
#     log_success(f"Fallback conversion OK — h264/aac, {f_info['width']}x{f_info['height']}")
#     return fallback_path, f_info


# def verify_prepared_output(path: str, info: dict):
#     faststart_ok = check_faststart(path)
#     log_info(
#         f"VERIFY -> container=mp4 video={info['video_codec']} audio={info['audio_codec']} "
#         f"width={info['width']} height={info['height']} "
#         f"duration={int(info['duration'])} size={human_size(info['size'])} "
#         f"faststart={'yes' if faststart_ok else ('no' if faststart_ok is False else 'unknown')}"
#     )
#     if info["video_codec"] != "h264":
#         log_warn(f"NOTE: final video codec is '{info['video_codec']}', not H.264 — "
#                   f"still not guaranteed to stream/seek on every device.")
#     return faststart_ok

# # # Cell — run_pipeline updated to accept the movie dict (for poster_url) alongside the URL

# # def run_pipeline(url, movie: dict = None) -> bool:
# #     filename = get_filename_from_headers(url)
# #     log_info(f"Detected filename: {filename}")

# #     is_archive, reason = is_archive_file(url, filename)
# #     if is_archive:
# #         log_warn(f"Skipping {filename}: detected as archive ({reason}).")
# #         return False

# #     ok, size_bytes = is_within_size_limit(url, MAX_SIZE_BYTES)

# #     if size_bytes is None:
# #         log_warn(f"Could not determine file size for {filename} — skipping to be safe.")
# #         return False

# #     if not ok:
# #         log_warn(f"Skipping {filename}: size {human_size(size_bytes)} exceeds 2GB limit.")
# #         return False

# #     log_info(f"Checks passed: not an archive, size {human_size(size_bytes)} (< 2GB) — proceeding with download.")

# #     dest_path = os.path.join(DOWNLOAD_DIR, filename)

# #     if not download_file(url, dest_path):
# #         log_error("Skipping due to download failure.")
# #         return False

# #     meta = get_video_metadata(dest_path)
# #     log_info(f"Metadata: {meta['width']}x{meta['height']} | "
# #               f"{format_duration(meta['duration'])} | {human_size(meta['size'])}")

# #     # --- Use the API poster instead of generating a thumbnail from the video ---
# #     poster_url = movie.get("poster_url") if movie else None
# #     thumb_path = download_poster_thumbnail(poster_url, dest_path)

# #     caption = (
# #         f"📁 Name: {filename}\n"
# #         f"📦 Size: {human_size(meta['size'])}\n"
# #         f"🎥 Resolution: {meta['width']}×{meta['height']}\n"
# #         f"⏱ Duration: {format_duration(meta['duration'])}\n"
# #     )

# #     success = upload_video(dest_path, thumb_path, caption, meta["duration"], meta["width"], meta["height"])

# #     if success:
# #         try:
# #             os.remove(dest_path)
# #             if thumb_path and os.path.exists(thumb_path):
# #                 os.remove(thumb_path)
# #             log_success("Local file(s) deleted. Ready for next download.")
# #         except Exception as e:
# #             log_warn(f"Cleanup issue: {e}")
# #         return True
# #     else:
# #         log_warn("Upload failed — file kept locally for retry.")
# #         return False




# def run_pipeline(url, move: dict = None) -> bool:
#     filename = get_filename_from_headers(url)
#     log_info(f"Detected filename: {filename}")

#     is_archive, reason = is_archive_file(url, filename)
#     if is_archive:
#         log_warn(f"Skipping {filename}: detected as archive ({reason}).")
#         return False

#     ok, size_bytes = is_within_size_limit(url, MAX_SIZE_BYTES)
#     if size_bytes is None:
#         log_warn(f"Could not determine file size for {filename} — skipping to be safe.")
#         return False
#     if not ok:
#         log_warn(f"Skipping {filename}: size {human_size(size_bytes)} exceeds 2GB limit.")
#         return False

#     log_info(f"Checks passed: not an archive, size {human_size(size_bytes)} (< 2GB) — proceeding with download.")

#     dest_path = os.path.join(DOWNLOAD_DIR, filename)

#     if not download_file(url, dest_path):
#         log_error("Skipping due to download failure.")
#         return False

#     # --- NEW: prepare video for reliable Telegram streaming ---
#     prepared_path, prepared_info = prepare_video_for_telegram(dest_path)
#     if prepared_path is None:
#         log_error("Could not produce a streamable file — source kept on disk for retry/inspection.")
#         return False

#     verify_prepared_output(prepared_path, prepared_info)

#     meta = get_video_metadata(prepared_path)
#     log_info(f"Final metadata: {meta['width']}x{meta['height']} | "
#               f"{format_duration(meta['duration'])} | {human_size(meta['size'])}")

#     poster_url = move.get("poster_url") if move else None
#     thumb_path = download_poster_thumbnail(poster_url, prepared_path)

#     caption = (
#         f"📁 Name: {filename}\n"
#         f"📦 Size: {human_size(meta['size'])}\n"
#         f"🎥 Resolution: {meta['width']}×{meta['height']}\n"
#         f"⏱ Duration: {format_duration(meta['duration'])}\n"
#     )

#     display_filename = os.path.splitext(filename)[0] + ".mp4"

#     success = upload_video(
#         prepared_path, thumb_path, caption,
#         meta["duration"], meta["width"], meta["height"],
#         display_filename=display_filename
#     )

#     if success:
#         try:
#             if os.path.exists(prepared_path):
#                 os.remove(prepared_path)
#             if prepared_path != dest_path and os.path.exists(dest_path):
#                 os.remove(dest_path)
#             if thumb_path and os.path.exists(thumb_path):
#                 os.remove(thumb_path)
#             log_success("Local file(s) deleted. Ready for next download.")
#         except Exception as e:
#             log_warn(f"Cleanup issue: {e}")
#         return True
#     else:
#         log_warn("Upload failed — source + prepared file(s) kept locally for retry.")
#         return False

# Cell 1 — Mount Google Drive
# from google.colab import drive
# drive.mount('/content/drive')

# # Cell 2 — Imports and config
# import requests
# import json
# import os
# import time
# from datetime import datetime

# API_URL = "https://zzlgmmtn-3000.inc1.devtunnels.ms/api/movies"
# API_URL2 = "https://zzlgmmtn-3000.inc1.devtunnels.ms"
# SEEN_LINKS_API_ENDPOINT = f"{API_URL2}/api/seen-links"

# # Persisted dedupe store on Drive — survives across Colab sessions
# # DRIVE_DIR = "/content/drive/MyDrive/movie_pipeline"

# # os.makedirs(DRIVE_DIR, exist_ok=True)

# # # Cell 3 — Seen-links store (load / check / add via API)

# def load_seen_links() -> set:
#     """Load the set of already-processed links from the API endpoint. Returns empty set if request fails."""
#     try:
#         response = requests.get(SEEN_LINKS_API_ENDPOINT, timeout=15)
#         if response.status_code == 200:
#             data = response.json()
#             if data.get("success", False):
#                 links = data.get("links", [])
#                 return set(links)
#         print(f"⚠️ Failed to load seen links from API, status code: {response.status_code}")
#     except Exception as e:
#         print(f"⚠️ Could not reach seen links API ({e}), starting fresh set.")
#     return set()


# def is_duplicate(link: str, seen: set) -> bool:
#     """Check whether a link has already been processed."""
#     return link in seen


# def mark_seen(link: str, seen: set) -> None:
#     """Add a link to the in-memory seen set and post it to the API endpoint to persist."""
#     cleaned_link = link.strip()
#     if not cleaned_link:
#         return

#     seen.add(cleaned_link)
#     try:
#         response = requests.post(
#             SEEN_LINKS_API_ENDPOINT,
#             json={"link": cleaned_link},
#             timeout=15
#         )
#         if response.status_code == 200:
#             data = response.json()
#             if not data.get("success", False):
#                 print(f"⚠️ API reported failure while adding link: {data.get('error', 'Unknown error')}")
#         else:
#             print(f"⚠️ Failed to persist link to API, status code: {response.status_code}")
#     except Exception as e:
#         print(f"⚠️ Could not reach seen links API to save link ({e}).")

# # Cell 4 — Fetch from API and extract links

# def fetch_movies(params: dict = None) -> list:
#     """
#     Calls the /api/movies endpoint and returns the list of movie objects.
#     params can include: search, quality, pageMin, pageMax, pageNum
#     """
#     try:
#         resp = requests.get(API_URL, params=params or {}, timeout=30)
#         resp.raise_for_status()
#         data = resp.json()
#         if not data.get("success"):
#             print(f"API returned success=False: {data}")
#             return []
#         return data.get("movies", [])
#     except requests.exceptions.RequestException as e:
#         print(f"Error fetching from API: {e}")
#         return []


# # Cell — Corrected link extraction: parses the nested JSON `links` field

# def extract_links(movie: dict) -> list[dict]:
#     """
#     Parses the movie's `links` field (a JSON string) and flattens it into
#     a list of individual link dicts: {quality_label, text, url}.
#     Returns [] if links field is missing/malformed.
#     """
#     raw = movie.get("links")
#     if not raw:
#         return []

#     try:
#         groups = json.loads(raw) if isinstance(raw, str) else raw
#     except (json.JSONDecodeError, TypeError) as e:
#         print(f"    Could not parse links JSON for '{movie.get('title')}': {e}")
#         return []

#     flattened = []
#     for group in groups:
#         quality_label = group.get("quality", "")
#         for link_obj in group.get("links", []):
#             url = link_obj.get("url")
#             if url:
#                 flattened.append({
#                     "quality_label": quality_label,
#                     "text": link_obj.get("text", ""),
#                     "url": url
#                 })

#     return flattened

# # Cell — Updated pipeline: full tracking + detailed summary at the end

# def run_pipeline_one_by_one(params: dict = None, process_fn=None, delay_seconds: float = 0):
#     """
#     Fetches movies, then processes EVERY individual link (a movie can have several)
#     one at a time: check duplicate -> process if new -> mark seen -> save to Drive immediately.
#     Tracks every link into categorized lists and prints a full summary at the end.
#     """
#     seen = load_seen_links()
#     print(f"Loaded {len(seen)} previously seen links from Drive")

#     movies = fetch_movies(params)
#     print(f"Fetched {len(movies)} movies from API\n")

#     # Track everything, not just counts
#     processed_ok = []      # successfully processed (new + handled without error)
#     skipped_dup = []       # already seen before this run
#     failed = []            # process_fn raised an error
#     no_link_movies = []    # movies with no extractable links

#     item_num = 0
#     total_links_found = 0

#     # First pass: count total links across all movies (for progress context)
#     all_movie_links = []
#     for movie in movies:
#         links = extract_links(movie)
#         if not links:
#             no_link_movies.append(movie.get("title", "Unknown"))
#             continue
#         for link_info in links:
#             all_movie_links.append((movie, link_info))
#     total_links_found = len(all_movie_links)

#     print(f"Total individual links found across all movies: {total_links_found}\n")

#     for movie, link_info in all_movie_links:
#         item_num += 1
#         title = movie.get("title", "Unknown")
#         url = link_info["url"]
#         quality = link_info.get("quality_label", "")
#         text = link_info.get("text", "")
#         label = f"{title} [{quality}] {text}"

#         remaining = total_links_found - item_num
#         print(f"[{item_num}/{total_links_found}] (remaining: {remaining}) {label}", end=" ... ")

#         if is_duplicate(url, seen):
#             print(f"SKIPPED (duplicate) -> {url}")
#             skipped_dup.append({"title": title, "quality": quality, "url": url})
#             continue

#         print(f"NEW -> {url}")

#         if process_fn:
#             try:
#                 process_fn(movie, link_info)
#             except Exception as e:
#                 print(f"    FAILED: {e}")
#                 failed.append({"title": title, "quality": quality, "url": url, "error": str(e)})
#                 continue  # not marked seen, retried next run

#         mark_seen(url, seen)
#         # save_seen_links(seen)  # persist after every single new link
#         processed_ok.append({"title": title, "quality": quality, "url": url})

#         if delay_seconds:
#             time.sleep(delay_seconds)

#     # --- Full summary ---
#     print("\n" + "=" * 60)
#     print("PIPELINE SUMMARY")
#     print("=" * 60)

#     print(f"\n✅ Successfully processed ({len(processed_ok)}):")
#     for item in processed_ok:
#         print(f"   - {item['title']} [{item['quality']}] -> {item['url']}")

#     print(f"\n⏭️  Skipped as duplicate ({len(skipped_dup)}):")
#     for item in skipped_dup:
#         print(f"   - {item['title']} [{item['quality']}] -> {item['url']}")

#     print(f"\n❌ Failed / remaining to retry ({len(failed)}):")
#     for item in failed:
#         print(f"   - {item['title']} [{item['quality']}] -> {item['url']}  (error: {item['error']})")

#     print(f"\n⚠️  Movies with no links at all ({len(no_link_movies)}):")
#     for t in no_link_movies:
#         print(f"   - {t}")

#     print("\n" + "-" * 60)
#     print(f"Total movies fetched:        {len(movies)}")
#     print(f"Total individual links:      {total_links_found}")
#     print(f"New & processed:             {len(processed_ok)}")
#     print(f"Skipped (already seen):      {len(skipped_dup)}")
#     print(f"Failed (will retry next run):{len(failed)}")
#     print(f"Movies with no links:        {len(no_link_movies)}")
#     print(f"Total seen links now:        {len(seen)}")
#     print("=" * 60)

#     return {
#         "processed_ok": processed_ok,
#         "skipped_dup": skipped_dup,
#         "failed": failed,
#         "no_link_movies": no_link_movies,
#         "total_links_found": total_links_found,
#     }

# # Cell — Handler updated to pass the movie dict through so poster_url is available

# def my_download_handler(movie: dict, link_info: dict):
#     url = link_info["url"]
#     title = movie.get("title", "Unknown")
#     quality = link_info.get("quality_label", "")

#     print(f"    -> Sending to downloader: {title} [{quality}]")

#     try:
#         success = run_pipeline(url, movie=movie)  # pass movie so poster_url is accessible
#     except Exception as e:
#         print(f"    Download pipeline failed for {url}: {e}")
#         raise

#     if success:
#         print(f"    Success — pausing 5s before next item...")
#         time.sleep(5)
#     else:
#         print(f"    Skipped/failed — no pause, moving to next item.")

# import os, sys, time, json, subprocess, requests
# from datetime import datetime
# from colorama import Fore, Style, init as colorama_init
# from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

# colorama_init(autoreset=True)

# # Cell — Run: fetch from API, dedupe, auto-download every new link one by one


# run_pipeline_one_by_one(process_fn=my_download_handler, delay_seconds=0.5)

# !nohup /content/telegram-bot-api \
#   --api-id=22219997 \
#   --api-hash=e3840aec1ee4daefa979d3ceeecba323 \
#   --local \
#   --http-port=8081 \
#   > telegram.log 2>&1 &

# @title 2. Configuration
# import os
# import sys
# import time
# import json
# import subprocess
# import requests
# import re
# import mimetypes
# from urllib.parse import urlparse, unquote
# from datetime import datetime
# from colorama import Fore, Style, init as colorama_init
# from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

# colorama_init(autoreset=True)

# # ====== TELEGRAM CONFIG ======
# API_ID = 22219997
# API_HASH = "e3840aec1ee4daefa979d3ceeecba323"
# BOT_TOKEN = "7585583046:AAESix1g0gpKbpCsF-XFQcb0fTzvSfoXW2o"
# CHAT_ID = "-1003349292789"

# # Set this to True if you are running the Local Bot API server for >50MB files
# USE_LOCAL_API = True

# if USE_LOCAL_API:
#     BOT_API = f"http://127.0.0.1:8081/bot{BOT_TOKEN}"
#     # Uncomment the block below if you want the notebook to launch the API server automatically
#     """
#     server_proc = subprocess.Popen(
#         [
#             "/content/telegram-bot-api",
#             f"--api-id={API_ID}",
#             f"--api-hash={API_HASH}",
#             "--local",
#             "--http-port=8081"
#         ],
#         stdout=subprocess.DEVNULL,
#         stderr=subprocess.DEVNULL
#     )
#     time.sleep(5)
#     print("Local Bot API server started, PID:", server_proc.pid)
#     """
# else:
#     BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# # ====== PIPELINE CONFIG ======
# DOWNLOAD_DIR = "/content/downloads"
# os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# MAX_RETRIES = 1
# MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB limit

# API_URL = "https://zzlgmmtn-3000.inc1.devtunnels.ms/api/movies"
# API_URL2 = "https://zzlgmmtn-3000.inc1.devtunnels.ms"
# SEEN_LINKS_API_ENDPOINT = f"{API_URL2}/api/seen-links"

# # ====== LOGGER HELPERS ======
# def log_info(msg): print(Fore.CYAN + "[INFO] " + Style.RESET_ALL + msg)
# def log_success(msg): print(Fore.GREEN + "[OK] " + Style.RESET_ALL + msg)
# def log_warn(msg): print(Fore.YELLOW + "[WARN] " + Style.RESET_ALL + msg)
# def log_error(msg): print(Fore.RED + "[ERROR] " + Style.RESET_ALL + msg)

# def human_size(n):
#     for unit in ["B","KB","MB","GB","TB"]:
#         if n < 1024: return f"{n:.2f} {unit}"
#         n /= 1024
#     return f"{n:.2f} PB"

# def format_duration(seconds):
#     h = seconds // 3600
#     m = (seconds % 3600) // 60
#     s = seconds % 60
#     return f"{h:02d}:{m:02d}:{s:02d}"

# @title 3. File Processing & Streaming Optimization Helpers (Fixed)

# def clean_filename(filename):
#     name, ext = os.path.splitext(filename)
#     name = name.replace(".", " ")
#     name = " ".join(name.split())

#     # Remove unwanted prefixes
#     name = re.sub(r"^Movies4u[\s_.-]*", "", name, flags=re.IGNORECASE)
#     name = re.sub(r"^\[.*?\]\s*", "", name, flags=re.IGNORECASE)
#     name = re.sub(r"^Foo[\s_.-]*", "", name, flags=re.IGNORECASE)

#     name = " ".join(name.split())
#     return name.strip() + ext

# def get_filename_from_headers(url):
#     try:
#         r = requests.head(url, allow_redirects=True, timeout=15)
#         headers = r.headers
#         if r.status_code >= 400 or "content-disposition" not in {k.lower() for k in headers.keys()}:
#             r2 = requests.get(url, stream=True, timeout=15)
#             headers = r2.headers
#             r2.close()
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Could not fetch headers, falling back to URL name.")
#         headers = {}

#     filename = None
#     cd = headers.get("Content-Disposition") or headers.get("content-disposition")
#     if cd:
#         match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
#         if not match: match = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
#         if match: filename = unquote(match.group(1).strip())

#     if not filename:
#         path = urlparse(url).path
#         candidate = os.path.basename(path)
#         if candidate and "." in candidate: filename = unquote(candidate)

#     if not filename:
#         content_type = headers.get("Content-Type", "").split(";")[0].strip()
#         ext = mimetypes.guess_extension(content_type) or ".mp4"
#         filename = f"video_{int(time.time())}{ext}"

#     filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
#     filename = clean_filename(filename)

#     if not os.path.splitext(filename)[1]:
#         filename += ".mp4"
#     return filename

# def get_video_metadata(path):
#     cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     data = json.loads(result.stdout)
#     video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
#     duration = float(data.get("format", {}).get("duration", 0))
#     width = int(video_stream.get("width", 0)) if video_stream else 0
#     height = int(video_stream.get("height", 0)) if video_stream else 0
#     size = int(data.get("format", {}).get("size", os.path.getsize(path)))
#     return {"duration": int(duration), "width": width, "height": height, "size": size}

# def get_video_mimetype(file_path: str) -> str:
#     mime_map = {
#         ".mp4": "video/mp4",
#         ".mkv": "video/x-matroska",
#         ".webm": "video/webm",
#         ".mov": "video/quicktime"
#     }
#     ext = os.path.splitext(file_path)[1].lower()
#     if ext in mime_map: return mime_map[ext]
#     guessed, _ = mimetypes.guess_type(file_path)
#     return guessed or "video/mp4"

# def optimize_video_for_streaming(input_path: str) -> str:
#     """
#     Applies Fast Start (moov atom) using a temporary output file to prevent
#     input/output collision errors, keeping all audio tracks and subtitles.
#     """
#     log_info("Applying Fast Start streaming optimization (keeping all audio & subtitles)...")

#     base, ext = os.path.splitext(input_path)
#     temp_output_path = f"{base}_temp_streamable{ext}"

#     try:
#         cmd = [
#             "ffmpeg", "-y", "-v", "error",
#             "-i", input_path,
#             "-map", "0",              # Maps all streams (video, audio, subtitles)
#             "-c", "copy",             # Stream copies everything without re-encoding
#             "-movflags", "+faststart",
#             temp_output_path
#         ]

#         result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

#         if result.returncode == 0 and os.path.exists(temp_output_path):
#             log_success("Streaming optimization applied successfully!")
#             os.remove(input_path)                 # Delete the original unoptimized file
#             os.rename(temp_output_path, input_path) # Rename temp file to target filename
#             return input_path
#         else:
#             log_warn(f"Optimization skipped. Proceeding with original file. {result.stderr}")
#             if os.path.exists(temp_output_path): os.remove(temp_output_path)
#             return input_path

#     except Exception as e:
#         log_error(f"FFmpeg exception: {e}")
#         if os.path.exists(temp_output_path): os.remove(temp_output_path)
#         return input_path

# @title 4. Downloader and Uploader Functions
# MAX_RETRIES = 1
# def download_file(url, dest_path):
#     for attempt in range(1, 1 + 1):
#         try:
#             resume_byte_pos = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
#             headers = {"Range": f"bytes={resume_byte_pos}-"} if resume_byte_pos else {}
#             if resume_byte_pos: log_warn(f"Resuming from {human_size(resume_byte_pos)}")

#             with requests.get(url, headers=headers, stream=True, timeout=30) as r:
#                 r.raise_for_status()
#                 total_size = int(r.headers.get("content-length", 0)) + resume_byte_pos
#                 mode = "ab" if resume_byte_pos else "wb"
#                 downloaded = resume_byte_pos
#                 start_time = time.time()

#                 with open(dest_path, mode) as f:
#                     for chunk in r.iter_content(chunk_size=1024*1024):
#                         if not chunk: continue
#                         f.write(chunk)
#                         downloaded += len(chunk)
#                         elapsed = time.time() - start_time
#                         speed = (downloaded - resume_byte_pos) / elapsed if elapsed > 0 else 0
#                         percent = (downloaded / total_size * 100) if total_size else 0
#                         eta = (total_size - downloaded) / speed if speed > 0 else 0

#                         bar_len = 30
#                         filled = int(bar_len * percent / 100)
#                         bar = "█"*filled + "-"*(bar_len-filled)
#                         sys.stdout.write(
#                             f"\r{Fore.BLUE}⬇ Downloading{Style.RESET_ALL} [{bar}] "
#                             f"{percent:5.1f}% | {human_size(downloaded)}/{human_size(total_size)} "
#                             f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
#                         )
#                         sys.stdout.flush()
#                 print()
#                 log_success(f"Download complete: {dest_path}")
#                 return True
#         except (requests.exceptions.RequestException, ConnectionError) as e:
#             log_error(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
#             time.sleep(3 * attempt)
#     return False

# def download_poster_thumbnail(poster_url: str, video_path: str, timeout: int = 20) -> str | None:
#     if not poster_url: return None
#     thumb_path = video_path + "_thumb.jpg"
#     try:
#         resp = requests.get(poster_url, timeout=timeout, stream=True)
#         resp.raise_for_status()
#         with open(thumb_path, "wb") as f:
#             for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
#         return thumb_path
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Poster download failed: {e}")
#         return None

# def upload_video(file_path, thumb_path, caption, duration, width, height):
#     file_size = os.path.getsize(file_path)
#     start_time = time.time()
#     last_print = [0]
#     video_mime = get_video_mimetype(file_path)

#     def create_callback(monitor):
#         def callback(m):
#             now = time.time()
#             if now - last_print[0] < 0.3 and m.bytes_read != m.len: return
#             last_print[0] = now
#             percent = m.bytes_read / m.len * 100
#             elapsed = now - start_time
#             speed = m.bytes_read / elapsed if elapsed > 0 else 0
#             eta = (m.len - m.bytes_read) / speed if speed > 0 else 0
#             bar_len = 30
#             filled = int(bar_len * percent / 100)
#             bar = "█"*filled + "-"*(bar_len-filled)
#             sys.stdout.write(
#                 f"\r{Fore.MAGENTA}⬆ Uploading{Style.RESET_ALL} [{bar}] "
#                 f"{percent:5.1f}% | {human_size(m.bytes_read)}/{human_size(m.len)} "
#                 f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
#             )
#             sys.stdout.flush()
#         return callback

#     fields = {
#         "chat_id": CHAT_ID,
#         "caption": caption,
#         "duration": str(duration),
#         "width": str(width),
#         "height": str(height),
#         "supports_streaming": "true", # Mandatory API Flag for Streaming
#         "video": (os.path.basename(file_path), open(file_path, "rb"), video_mime),
#     }
#     if thumb_path and os.path.exists(thumb_path):
#         fields["thumb"] = (os.path.basename(thumb_path), open(thumb_path, "rb"), "image/jpeg")

#     encoder = MultipartEncoder(fields=fields)
#     monitor = MultipartEncoderMonitor(encoder, create_callback(encoder))

#     try:
#         response = requests.post(
#             f"{BOT_API}/sendVideo",
#             data=monitor,
#             headers={"Content-Type": monitor.content_type},
#             timeout=None
#         )
#         print()
#         result = response.json()
#         if result.get("ok"):
#             log_success(f"Upload verified — message_id: {result['result']['message_id']}")
#             return True
#         else:
#             log_error(f"Upload failed: {result}")
#             return False
#     except Exception as e:
#         print()
#         log_error(f"Upload exception: {e}")
#         return False

# @title 5. API Fetching, Duplicate Checking & Main Pipeline


# SKIP_EXTENSIONS = {".zip", ".rar", ".7z"}


# def is_archive_file(url: str, filename: str) -> tuple[bool, str]:
#     ext = os.path.splitext(filename)[1].lower()
#     if ext in SKIP_EXTENSIONS:
#         return True, f"extension '{ext}'"
#     try:
#         resp = requests.head(url, timeout=15, allow_redirects=True)
#         ct = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
#         if ct in {
#             "application/zip",
#             "application/x-zip-compressed",
#             "application/x-rar-compressed",
#             "application/x-7z-compressed",
#         }:
#             return True, f"content-type '{ct}'"
#     except Exception:
#         pass
#     return False, ""


# def get_remote_file_size(url: str) -> int | None:
#     try:
#         resp = requests.head(url, timeout=15, allow_redirects=True)
#         if resp.headers.get("Content-Length", "").isdigit():
#             return int(resp.headers.get("Content-Length"))

#         resp = requests.get(url, timeout=15, stream=True, headers={"Range": "bytes=0-0"})
#         if resp.headers.get("Content-Range", "").split("/")[-1].isdigit():
#             return int(resp.headers.get("Content-Range").split("/")[-1])
#     except Exception:
#         pass
#     return None


# def is_within_size_limit(url: str, max_bytes: int = MAX_SIZE_BYTES):
#     size = get_remote_file_size(url)
#     return (False, None) if size is None else (size < max_bytes, size)


# def load_seen_links() -> set:
#     try:
#         resp = requests.get(SEEN_LINKS_API_ENDPOINT, timeout=15)
#         if resp.status_code == 200 and resp.json().get("success"):
#             return set(resp.json().get("links", []))
#     except Exception:
#         pass
#     return set()


# def mark_seen(link: str, seen: set):
#     cleaned = link.strip()
#     if not cleaned:
#         return
#     seen.add(cleaned)
#     try:
#         requests.post(SEEN_LINKS_API_ENDPOINT, json={"link": cleaned}, timeout=15)
#     except Exception:
#         pass


# def extract_links(movie: dict) -> list[dict]:
#     raw = movie.get("links")
#     if not raw:
#         return []
#     try:
#         groups = json.loads(raw) if isinstance(raw, str) else raw
#     except Exception:
#         return []

#     flattened = []
#     for group in groups:
#         quality_label = group.get("quality", "")
#         for link_obj in group.get("links", []):
#             if link_obj.get("url"):
#                 flattened.append({
#                     "quality_label": quality_label,
#                     "text": link_obj.get("text", ""),
#                     "url": link_obj.get("url"),
#                 })
#     return flattened


# def run_pipeline(url: str, movie: dict = None) -> tuple[bool, bool]:
#     """
#     Returns:
#         (success: bool, should_mark_seen: bool)
#     """
#     dest_path = None
#     thumb_path = None
#     try:
#         filename = get_filename_from_headers(url)
#         is_archive, reason = is_archive_file(url, filename)
#         if is_archive:
#             log_warn(f"Skipping {filename}: detected as archive ({reason}).")
#             return False, True  # Archive file -> Mark seen immediately

#         ok, size_bytes = is_within_size_limit(url)
#         if size_bytes is not None and not ok:
#             log_warn(f"Skipping {filename}: Size ({human_size(size_bytes)}) exceeds 2GB limit.")
#             return False, True  # Exceeds size limit -> Mark seen immediately

#         if size_bytes is None:
#             log_warn(f"Could not verify file size for {filename}. Proceeding with attempt...")

#         dest_path = os.path.join(DOWNLOAD_DIR, filename)

#         # Remove existing partial file from prior attempt if present
#         if os.path.exists(dest_path):
#             try:
#                 os.remove(dest_path)
#             except Exception:
#                 pass

#         if not download_file(url, dest_path):
#             return False, False  # Download failed

#         # Run Streaming Optimization Step
#         dest_path = optimize_video_for_streaming(dest_path)

#         # Grab Metadata after optimization
#         meta = get_video_metadata(dest_path)
#         poster_url = movie.get("poster_url") if movie else None
#         thumb_path = download_poster_thumbnail(poster_url, dest_path)

#         caption = (
#             f"📁 Name: {os.path.basename(dest_path)}\n"
#             f"📦 Size: {human_size(meta['size'])}\n"
#             f"🎥 Resolution: {meta['width']}×{meta['height']}\n"
#             f"⏱ Duration: {format_duration(meta['duration'])}\n"
#         )

#         success = upload_video(
#             dest_path, thumb_path, caption, meta["duration"], meta["width"], meta["height"]
#         )

#         if success:
#             return True, True  # Success -> Mark seen
#         return False, False  # Upload failed

#     except Exception as e:
#         log_warn(f"Pipeline error for {url}: {e}")
#         return False, False
#     finally:
#         # Guarantee cleanup after every attempt
#         try:
#             if dest_path and os.path.exists(dest_path):
#                 os.remove(dest_path)
#             if thumb_path and os.path.exists(thumb_path):
#                 os.remove(thumb_path)
#         except Exception:
#             pass


# def run_pipeline_one_by_one(process_fn=None, delay_seconds: float = 0, max_retries: int = 1):
#     seen = load_seen_links()
#     try:
#         movies = requests.get(API_URL, timeout=30).json().get("movies", [])
#     except Exception:
#         movies = []

#     all_movie_links = []
#     for movie in movies:
#         for link_info in extract_links(movie):
#             all_movie_links.append((movie, link_info))

#     total_links = len(all_movie_links)

#     # Filter out already seen links in bulk upfront
#     unseen_links = [
#         (movie, link_info)
#         for movie, link_info in all_movie_links
#         if link_info["url"] not in seen
#     ]

#     skipped_count = total_links - len(unseen_links)
#     print(f"Total links fetched: {total_links}")
#     print(f"Already processed (skipped): {skipped_count}")
#     print(f"Remaining to download: {len(unseen_links)}\n")

#     # Process remaining links one by one
#     for i, (movie, link_info) in enumerate(unseen_links, 1):
#         url = link_info["url"]

#         if url in seen:
#             continue

#         print(
#             f"[{i}/{len(unseen_links)}] Processing: {movie.get('title')} [{link_info.get('quality_label')}]"
#         )

#         success = False
#         should_mark_seen = False

#         for attempt in range(1, max_retries + 1):
#             try:
#                 res = process_fn(movie, link_info) if process_fn else (False, False)

#                 if isinstance(res, tuple):
#                     success, should_mark_seen = res
#                 elif isinstance(res, bool):
#                     success, should_mark_seen = res, res
#                 else:
#                     success, should_mark_seen = False, False

#                 if success:
#                     mark_seen(url, seen)
#                     print("SUCCESS: Uploaded and marked as seen.\n")
#                     break

#                 if should_mark_seen:
#                     mark_seen(url, seen)
#                     print("SKIPPED & MARKED SEEN: File exceeds size limit or is an archive.\n")
#                     break

#                 print(f"Attempt {attempt}/{max_retries} failed.")
#             except Exception as e:
#                 print(f"Attempt {attempt}/{max_retries} ERROR: {e}")

#             if attempt < max_retries:
#                 time.sleep(2)

#         # Force mark seen immediately if failed or errored out on attempt 1
#         if not success and url not in seen:
#             print("FAILED/ERROR: Marking link as seen to skip future retries.\n")
#             mark_seen(url, seen)

#         if delay_seconds:
#             time.sleep(delay_seconds)


# def my_download_handler(movie: dict, link_info: dict):
#     return run_pipeline(link_info["url"], movie=movie)

# @title 6. Run Execution
# run_pipeline_one_by_one(process_fn=my_download_handler, delay_seconds=1.0)

# # @title 2. Configuration
# import os
# import sys
# import time
# import json
# import subprocess
# import requests
# import re
# import mimetypes
# from urllib.parse import urlparse, unquote
# from datetime import datetime
# from colorama import Fore, Style, init as colorama_init

# from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

# colorama_init(autoreset=True)

# # ====== TELEGRAM CONFIG ======
# API_ID = 22219997
# API_HASH = "e3840aec1ee4daefa979d3ceeecba323"
# BOT_TOKEN = "7585583046:AAESix1g0gpKbpCsF-XFQcb0fTzvSfoXW2o"
# CHAT_ID = "-1003349292789"

# # Set this to True if you are running the Local Bot API server for >50MB files
# USE_LOCAL_API = True

# if USE_LOCAL_API:
#     BOT_API = f"http://127.0.0.1:8081/bot{BOT_TOKEN}"
# else:
#     BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# # ====== PIPELINE CONFIG ======
# DOWNLOAD_DIR = "/content/downloads"
# os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# MAX_RETRIES = 1
# MAX_SIZE_BYTES_NORMAL = 2 * 1024 * 1024 * 1024  # 2GB limit for normal movies


# # API_URL = "https://zzlgmmtn-3000.inc1.devtunnels.ms/api/movies"
# # API_URL2 = "https://zzlgmmtn-3000.inc1.devtunnels.ms"

# API_URL = "https://movie-scraper-v2.onrender.com/api/movies-to-download"
# API_URL2 = "https://movie-scraper-v2.onrender.com"

# SEEN_LINKS_API_ENDPOINT = f"{API_URL2}/api/seen-links"

# # ====== LOGGER HELPERS ======
# def log_info(msg): print(Fore.CYAN + "[INFO] " + Style.RESET_ALL + msg)
# def log_success(msg): print(Fore.GREEN + "[OK] " + Style.RESET_ALL + msg)
# def log_warn(msg): print(Fore.YELLOW + "[WARN] " + Style.RESET_ALL + msg)
# def log_error(msg): print(Fore.RED + "[ERROR] " + Style.RESET_ALL + msg)

# def human_size(n):
#     for unit in ["B","KB","MB","GB","TB"]:
#         if n < 1024: return f"{n:.2f} {unit}"
#         n /= 1024
#     return f"{n:.2f} PB"

# def format_duration(seconds):
#     h = int(seconds // 3600)
#     m = int((seconds % 3600) // 60)
#     s = int(seconds % 60)
#     return f"{h:02d}:{m:02d}:{s:02d}"

# # @title 3. File Processing & Streaming Optimization Helpers

# def clean_filename(filename):
#     name, ext = os.path.splitext(filename)
#     name = name.replace(".", " ")
#     name = " ".join(name.split())

#     # Remove unwanted prefixes
#     name = re.sub(r"^Movies4u[\s_.-]*", "", name, flags=re.IGNORECASE)
#     name = re.sub(r"^\[.*?\]\s*", "", name, flags=re.IGNORECASE)
#     name = re.sub(r"^Foo[\s_.-]*", "", name, flags=re.IGNORECASE)

#     name = " ".join(name.split())
#     return name.strip() + ext

# def get_filename_from_headers(url):
#     try:
#         r = requests.head(url, allow_redirects=True, timeout=15)
#         headers = r.headers
#         if r.status_code >= 400 or "content-disposition" not in {k.lower() for k in headers.keys()}:
#             r2 = requests.get(url, stream=True, timeout=15)
#             headers = r2.headers
#             r2.close()
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Could not fetch headers, falling back to URL name.")
#         headers = {}

#     filename = None
#     cd = headers.get("Content-Disposition") or headers.get("content-disposition")
#     if cd:
#         match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
#         if not match: match = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
#         if match: filename = unquote(match.group(1).strip())

#     if not filename:
#         path = urlparse(url).path
#         candidate = os.path.basename(path)
#         if candidate and "." in candidate: filename = unquote(candidate)

#     if not filename:
#         content_type = headers.get("Content-Type", "").split(";")[0].strip()
#         ext = mimetypes.guess_extension(content_type) or ".mp4"
#         filename = f"video_{int(time.time())}{ext}"

#     filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
#     filename = clean_filename(filename)

#     if not os.path.splitext(filename)[1]:
#         filename += ".mp4"
#     return filename

# def get_video_metadata(path):
#     cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     data = json.loads(result.stdout)
#     video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
#     duration = float(data.get("format", {}).get("duration", 0))
#     width = int(video_stream.get("width", 0)) if video_stream else 0
#     height = int(video_stream.get("height", 0)) if video_stream else 0
#     size = int(data.get("format", {}).get("size", os.path.getsize(path)))
#     return {"duration": int(duration), "width": width, "height": height, "size": size}

# def get_video_mimetype(file_path: str) -> str:
#     mime_map = {
#         ".mp4": "video/mp4",
#         ".mkv": "video/x-matroska",
#         ".webm": "video/webm",
#         ".mov": "video/quicktime"
#     }
#     ext = os.path.splitext(file_path)[1].lower()
#     if ext in mime_map: return mime_map[ext]
#     guessed, _ = mimetypes.guess_type(file_path)
#     return guessed or "video/mp4"

# def optimize_video_for_streaming(input_path: str) -> str:
#     """
#     Applies Fast Start (moov atom) using a temporary output file to prevent
#     input/output collision errors, keeping all audio tracks and subtitles.
#     """
#     log_info("Applying Fast Start streaming optimization (keeping all audio & subtitles)...")

#     base, ext = os.path.splitext(input_path)
#     temp_output_path = f"{base}_temp_streamable{ext}"

#     try:
#         cmd = [
#             "ffmpeg", "-y", "-v", "error",
#             "-i", input_path,
#             "-map", "0",              # Maps all streams (video, audio, subtitles)
#             "-c", "copy",             # Stream copies everything without re-encoding
#             "-movflags", "+faststart",
#             temp_output_path
#         ]

#         result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

#         if result.returncode == 0 and os.path.exists(temp_output_path):
#             log_success("Streaming optimization applied successfully!")
#             os.remove(input_path)                 # Delete original file
#             os.rename(temp_output_path, input_path) # Rename temp file to target filename
#             return input_path
#         else:
#             log_warn(f"Optimization skipped. Proceeding with original file. {result.stderr}")
#             if os.path.exists(temp_output_path): os.remove(temp_output_path)
#             return input_path

#     except Exception as e:
#         log_error(f"FFmpeg exception: {e}")
#         if os.path.exists(temp_output_path): os.remove(temp_output_path)
#         return input_path


# # @title 4. Downloader and Uploader Functions
# MAX_RETRIES = 1
# def download_file(url, dest_path):
#     for attempt in range(1, 1 + 1):
#         try:
#             resume_byte_pos = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
#             headers = {"Range": f"bytes={resume_byte_pos}-"} if resume_byte_pos else {}
#             if resume_byte_pos: log_warn(f"Resuming from {human_size(resume_byte_pos)}")

#             with requests.get(url, headers=headers, stream=True, timeout=30) as r:
#                 r.raise_for_status()
#                 total_size = int(r.headers.get("content-length", 0)) + resume_byte_pos
#                 mode = "ab" if resume_byte_pos else "wb"
#                 downloaded = resume_byte_pos
#                 start_time = time.time()

#                 with open(dest_path, mode) as f:
#                     for chunk in r.iter_content(chunk_size=1024*1024):
#                         if not chunk: continue
#                         f.write(chunk)
#                         downloaded += len(chunk)
#                         elapsed = time.time() - start_time
#                         speed = (downloaded - resume_byte_pos) / elapsed if elapsed > 0 else 0
#                         percent = (downloaded / total_size * 100) if total_size else 0
#                         eta = (total_size - downloaded) / speed if speed > 0 else 0

#                         bar_len = 30
#                         filled = int(bar_len * percent / 100)
#                         bar = "█"*filled + "-"*(bar_len-filled)
#                         sys.stdout.write(
#                             f"\r{Fore.BLUE}⬇ Downloading{Style.RESET_ALL} [{bar}] "
#                             f"{percent:5.1f}% | {human_size(downloaded)}/{human_size(total_size)} "
#                             f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
#                         )
#                         sys.stdout.flush()
#                 print()
#                 log_success(f"Download complete: {dest_path}")
#                 return True
#         except (requests.exceptions.RequestException, ConnectionError) as e:
#             log_error(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
#             time.sleep(3 * attempt)
#     return False

# def download_poster_thumbnail(poster_url: str, video_path: str, timeout: int = 20) -> str | None:
#     if not poster_url: return None
#     thumb_path = video_path + "_thumb.jpg"
#     try:
#         resp = requests.get(poster_url, timeout=timeout, stream=True)
#         resp.raise_for_status()
#         with open(thumb_path, "wb") as f:
#             for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
#         return thumb_path
#     except requests.exceptions.RequestException as e:
#         log_warn(f"Poster download failed: {e}")
#         return None

# def upload_video(file_path, thumb_path, caption, duration, width, height):
#     file_size = os.path.getsize(file_path)
#     start_time = time.time()
#     last_print = [0]
#     video_mime = get_video_mimetype(file_path)

#     def create_callback(monitor):
#         def callback(m):
#             now = time.time()
#             if now - last_print[0] < 0.3 and m.bytes_read != m.len: return
#             last_print[0] = now
#             percent = m.bytes_read / m.len * 100
#             elapsed = now - start_time
#             speed = m.bytes_read / elapsed if elapsed > 0 else 0
#             eta = (m.len - m.bytes_read) / speed if speed > 0 else 0
#             bar_len = 30
#             filled = int(bar_len * percent / 100)
#             bar = "█"*filled + "-"*(bar_len-filled)
#             sys.stdout.write(
#                 f"\r{Fore.MAGENTA}⬆ Uploading{Style.RESET_ALL} [{bar}] "
#                 f"{percent:5.1f}% | {human_size(m.bytes_read)}/{human_size(m.len)} "
#                 f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
#             )
#             sys.stdout.flush()
#         return callback

#     fields = {
#         "chat_id": CHAT_ID,
#         "caption": caption,
#         "duration": str(duration),
#         "width": str(width),
#         "height": str(height),
#         "supports_streaming": "true", # Mandatory API Flag for Streaming
#         "video": (os.path.basename(file_path), open(file_path, "rb"), video_mime),
#     }
#     if thumb_path and os.path.exists(thumb_path):
#         fields["thumb"] = (os.path.basename(thumb_path), open(thumb_path, "rb"), "image/jpeg")

#     encoder = MultipartEncoder(fields=fields)
#     monitor = MultipartEncoderMonitor(encoder, create_callback(encoder))

#     try:
#         response = requests.post(
#             f"{BOT_API}/sendVideo",
#             data=monitor,
#             headers={"Content-Type": monitor.content_type},
#             timeout=None
#         )
#         print()
#         result = response.json()
#         if result.get("ok"):
#             log_success(f"Upload verified — message_id: {result['result']['message_id']}")
#             return True
#         else:
#             log_error(f"Upload failed: {result}")
#             return False
#     except Exception as e:
#         print()
#         log_error(f"Upload exception: {e}")
#         return False

# # @title 5. API Fetching, Duplicate Checking & Main Pipeline

# SKIP_EXTENSIONS = {".zip", ".rar", ".7z"}

# def is_archive_file(url: str, filename: str) -> tuple[bool, str]:
#     ext = os.path.splitext(filename)[1].lower()
#     if ext in SKIP_EXTENSIONS:
#         return True, f"extension '{ext}'"
#     try:
#         resp = requests.head(url, timeout=15, allow_redirects=True)
#         ct = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
#         if ct in {
#             "application/zip",
#             "application/x-zip-compressed",
#             "application/x-rar-compressed",
#             "application/x-7z-compressed",
#         }:
#             return True, f"content-type '{ct}'"
#     except Exception:
#         pass
#     return False, ""

# def get_remote_file_size(url: str) -> int | None:
#     try:
#         resp = requests.head(url, timeout=15, allow_redirects=True)
#         if resp.headers.get("Content-Length", "").isdigit():
#             return int(resp.headers.get("Content-Length"))

#         resp = requests.get(url, timeout=15, stream=True, headers={"Range": "bytes=0-0"})
#         if resp.headers.get("Content-Range", "").split("/")[-1].isdigit():
#             return int(resp.headers.get("Content-Range").split("/")[-1])
#     except Exception:
#         pass
#     return None

# def is_within_size_limit(url: str):
#     size = get_remote_file_size(url)
#     return (False, None) if size is None else (size <= MAX_SIZE_BYTES_NORMAL, size)

# def load_seen_links() -> set:
#     try:
#         resp = requests.get(SEEN_LINKS_API_ENDPOINT, timeout=15)
#         if resp.status_code == 200 and resp.json().get("success"):
#             return set(resp.json().get("links", []))
#     except Exception:
#         pass
#     return set()

# def mark_seen(link: str, seen: set):
#     cleaned = link.strip()
#     if not cleaned:
#         return
#     seen.add(cleaned)
#     try:
#         requests.post(SEEN_LINKS_API_ENDPOINT, json={"link": cleaned}, timeout=15)
#     except Exception:
#         pass

# def extract_links(movie: dict) -> list[dict]:
#     raw = movie.get("links")
#     if not raw:
#         return []
#     try:
#         groups = json.loads(raw) if isinstance(raw, str) else raw
#     except Exception:
#         return []

#     flattened = []
#     for group in groups:
#         quality_label = group.get("quality", "")
#         for link_obj in group.get("links", []):
#             if link_obj.get("url"):
#                 flattened.append({
#                     "quality_label": quality_label,
#                     "text": link_obj.get("text", ""),
#                     "url": link_obj.get("url"),
#                 })
#     return flattened

# def run_pipeline(url: str, movie: dict = None) -> tuple[bool, bool]:
#     """
#     Returns:
#         (success: bool, should_mark_seen: bool)
#     """
#     dest_path = None
#     thumb_path = None
#     try:
#         filename = get_filename_from_headers(url)
#         is_archive, reason = is_archive_file(url, filename)
#         if is_archive:
#             log_warn(f"Skipping {filename}: detected as archive ({reason}).")
#             return False, True  # Archive file -> Mark seen immediately

#         ok, size_bytes = is_within_size_limit(url)
#         if size_bytes is not None and not ok:
#             log_warn(f"Skipping {filename}: Size ({human_size(size_bytes)}) exceeds 2GB limit.")
#             return False, True  # Mark seen so it's not retried

#         if size_bytes is None:
#             log_warn(f"Could not verify file size for {filename}. Proceeding with attempt...")

#         dest_path = os.path.join(DOWNLOAD_DIR, filename)

#         # Remove existing partial file from prior attempt if present
#         if os.path.exists(dest_path):
#             try:
#                 os.remove(dest_path)
#             except Exception:
#                 pass

#         if not download_file(url, dest_path):
#             return False, False  # Download failed

#         # Apply FastStart streaming optimization
#         dest_path = optimize_video_for_streaming(dest_path)

#         # Grab Metadata after optimization / compression
#         meta = get_video_metadata(dest_path)
#         poster_url = movie.get("poster_url") if movie else None
#         thumb_path = download_poster_thumbnail(poster_url, dest_path)

#         caption = (
#             f"📁 Name: {os.path.basename(dest_path)}\n"
#             f"📦 Size: {human_size(meta['size'])}\n"
#             f"🎥 Resolution: {meta['width']}×{meta['height']}\n"
#             f"⏱ Duration: {format_duration(meta['duration'])}\n"
#         )

#         success = upload_video(
#             dest_path, thumb_path, caption, meta["duration"], meta["width"], meta["height"]
#         )

#         if success:
#             return True, True  # Success -> Mark seen
#         return False, False  # Upload failed

#     except Exception as e:
#         log_warn(f"Pipeline error for {url}: {e}")
#         return False, False
#     finally:
#         # Guarantee cleanup after every attempt
#         try:
#             if dest_path and os.path.exists(dest_path):
#                 os.remove(dest_path)
#             if thumb_path and os.path.exists(thumb_path):
#                 os.remove(thumb_path)
#         except Exception:
#             pass

# def run_pipeline_one_by_one(process_fn=None, delay_seconds: float = 0, max_retries: int = 1):
#     seen = load_seen_links()
#     try:
#         movies = requests.get(API_URL, timeout=30).json().get("movies", [])
#     except Exception:
#         movies = []

#     # Sort movies by page_num ASC, id ASC
#     movies.sort(key=lambda m: (m.get("page_num", 9999), m.get("id", 0)))

#     all_movie_links = []
#     for movie in movies:
#         for link_info in extract_links(movie):
#             all_movie_links.append((movie, link_info))

#     total_links = len(all_movie_links)

#     # Filter out already seen links in bulk upfront
#     unseen_links = [
#         (movie, link_info)
#         for movie, link_info in all_movie_links
#         if link_info["url"] not in seen
#     ]

#     skipped_count = total_links - len(unseen_links)
#     print(f"Total links fetched: {total_links}")
#     print(f"Already processed (skipped): {skipped_count}")
#     print(f"Remaining to process: {len(unseen_links)}\n")

#     # Process remaining links one by one
#     for i, (movie, link_info) in enumerate(unseen_links, 1):
#         url = link_info["url"]

#         if url in seen:
#             continue

#         print(
#             f"[{i}/{len(unseen_links)}] Processing (Pg {movie.get('page_num', '?')}): {movie.get('title')} [{link_info.get('quality_label')}]"
#         )

#         success = False
#         should_mark_seen = False

#         for attempt in range(1, max_retries + 1):
#             try:
#                 res = process_fn(movie, link_info) if process_fn else (False, False)

#                 if isinstance(res, tuple):
#                     success, should_mark_seen = res
#                 elif isinstance(res, bool):
#                     success, should_mark_seen = res, res
#                 else:
#                     success, should_mark_seen = False, False

#                 if success:
#                     mark_seen(url, seen)
#                     print("SUCCESS: Uploaded and marked as seen.\n")
#                     break

#                 if should_mark_seen:
#                     mark_seen(url, seen)
#                     print("SKIPPED & MARKED SEEN: Archive file.\n")
#                     break

#                 print(f"Attempt {attempt}/{max_retries} failed.")
#             except Exception as e:
#                 print(f"Attempt {attempt}/{max_retries} ERROR: {e}")

#             if attempt < max_retries:
#                 time.sleep(2)

#         if not success and not should_mark_seen:
#             mark_seen(url, seen)
#             print("SKIPPED / FAILED: File exceeded size limit or error. Marked seen to prevent future retries.\n")

#         if delay_seconds:
#             time.sleep(delay_seconds)

# def my_download_handler(movie: dict, link_info: dict):
#     return run_pipeline(link_info["url"], movie=movie)

# # @title 6. Run Execution
# run_pipeline_one_by_one(process_fn=my_download_handler, delay_seconds=1.0)


!pip install pymongo dnspython

# @title 2. Configuration
import os
import sys
import time
import json
import subprocess
import requests
import re
import mimetypes
from urllib.parse import urlparse, unquote
from datetime import datetime
from colorama import Fore, Style, init as colorama_init
from pymongo import MongoClient

from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

# ====== MONGODB CONFIG ======
MONGO_URI = "mongodb+srv://karangade6630_db_user:PH3mTb73zv9yUZrw@movie-scraper-data.j3z6hjh.mongodb.net/"
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client['movie_scraper']
    seen_links_col = db["seen_links"]
    movies_col = db["movies"]
except Exception as e:
    print(f"[ERROR] Failed to connect to MongoDB: {e}")
    mongo_client = None
    seen_links_col = None
    movies_col = None

colorama_init(autoreset=True)

# ====== TELEGRAM CONFIG ======
API_ID = 22219997
API_HASH = "e3840aec1ee4daefa979d3ceeecba323"
BOT_TOKEN = "7585583046:AAESix1g0gpKbpCsF-XFQcb0fTzvSfoXW2o"
CHAT_ID = "-1003349292789"

# Set this to True if you are running the Local Bot API server for >50MB files
USE_LOCAL_API = True

if USE_LOCAL_API:
    BOT_API = f"http://127.0.0.1:8081/bot{BOT_TOKEN}"
else:
    BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ====== PIPELINE CONFIG ======
DOWNLOAD_DIR = "/content/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
MAX_RETRIES = 1
MAX_SIZE_BYTES_NORMAL = 2 * 1024 * 1024 * 1024  # 2GB limit for normal movies


# Fully migrated to MongoDB (movies_col & seen_links_col)

# ====== LOGGER HELPERS ======
def log_info(msg): print(Fore.CYAN + "[INFO] " + Style.RESET_ALL + msg)
def log_success(msg): print(Fore.GREEN + "[OK] " + Style.RESET_ALL + msg)
def log_warn(msg): print(Fore.YELLOW + "[WARN] " + Style.RESET_ALL + msg)
def log_error(msg): print(Fore.RED + "[ERROR] " + Style.RESET_ALL + msg)

def human_size(n):
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024: return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# @title 3. File Processing & Streaming Optimization Helpers

def clean_filename(filename):
    name, ext = os.path.splitext(filename)
    name = name.replace(".", " ")
    name = " ".join(name.split())

    # Remove unwanted prefixes
    name = re.sub(r"^Movies4u[\s_.-]*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\[.*?\]\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^Foo[\s_.-]*", "", name, flags=re.IGNORECASE)

    name = " ".join(name.split())
    return name.strip() + ext

def get_filename_from_headers(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=15)
        headers = r.headers
        if r.status_code >= 400 or "content-disposition" not in {k.lower() for k in headers.keys()}:
            r2 = requests.get(url, stream=True, timeout=15)
            headers = r2.headers
            r2.close()
    except requests.exceptions.RequestException as e:
        log_warn(f"Could not fetch headers, falling back to URL name.")
        headers = {}

    filename = None
    cd = headers.get("Content-Disposition") or headers.get("content-disposition")
    if cd:
        match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
        if not match: match = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
        if match: filename = unquote(match.group(1).strip())

    if not filename:
        path = urlparse(url).path
        candidate = os.path.basename(path)
        if candidate and "." in candidate: filename = unquote(candidate)

    if not filename:
        content_type = headers.get("Content-Type", "").split(";")[0].strip()
        ext = mimetypes.guess_extension(content_type) or ".mp4"
        filename = f"video_{int(time.time())}{ext}"

    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    filename = clean_filename(filename)

    if not os.path.splitext(filename)[1]:
        filename += ".mp4"
    return filename

def get_video_metadata(path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    duration = float(data.get("format", {}).get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    size = int(data.get("format", {}).get("size", os.path.getsize(path)))
    return {"duration": int(duration), "width": width, "height": height, "size": size}

def get_video_mimetype(file_path: str) -> str:
    mime_map = {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".mov": "video/quicktime"
    }
    ext = os.path.splitext(file_path)[1].lower()
    if ext in mime_map: return mime_map[ext]
    guessed, _ = mimetypes.guess_type(file_path)
    return guessed or "video/mp4"

def optimize_video_for_streaming(input_path: str) -> str:
    """
    Applies Fast Start (moov atom) using a temporary output file to prevent
    input/output collision errors, keeping all audio tracks and subtitles.
    """
    log_info("Applying Fast Start streaming optimization (keeping all audio & subtitles)...")

    base, ext = os.path.splitext(input_path)
    temp_output_path = f"{base}_temp_streamable{ext}"

    try:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", input_path,
            "-map", "0",              # Maps all streams (video, audio, subtitles)
            "-c", "copy",             # Stream copies everything without re-encoding
            "-movflags", "+faststart",
            temp_output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0 and os.path.exists(temp_output_path):
            log_success("Streaming optimization applied successfully!")
            os.remove(input_path)                 # Delete original file
            os.rename(temp_output_path, input_path) # Rename temp file to target filename
            return input_path
        else:
            log_warn(f"Optimization skipped. Proceeding with original file. {result.stderr}")
            if os.path.exists(temp_output_path): os.remove(temp_output_path)
            return input_path

    except Exception as e:
        log_error(f"FFmpeg exception: {e}")
        if os.path.exists(temp_output_path): os.remove(temp_output_path)
        return input_path


# @title 4. Downloader and Uploader Functions
MAX_RETRIES = 1
def download_file(url, dest_path):
    for attempt in range(1, 1 + 1):
        try:
            resume_byte_pos = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            headers = {"Range": f"bytes={resume_byte_pos}-"} if resume_byte_pos else {}
            if resume_byte_pos: log_warn(f"Resuming from {human_size(resume_byte_pos)}")

            with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0)) + resume_byte_pos
                mode = "ab" if resume_byte_pos else "wb"
                downloaded = resume_byte_pos
                start_time = time.time()

                with open(dest_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if not chunk: continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start_time
                        speed = (downloaded - resume_byte_pos) / elapsed if elapsed > 0 else 0
                        percent = (downloaded / total_size * 100) if total_size else 0
                        eta = (total_size - downloaded) / speed if speed > 0 else 0

                        bar_len = 30
                        filled = int(bar_len * percent / 100)
                        bar = "█"*filled + "-"*(bar_len-filled)
                        sys.stdout.write(
                            f"\r{Fore.BLUE}⬇ Downloading{Style.RESET_ALL} [{bar}] "
                            f"{percent:5.1f}% | {human_size(downloaded)}/{human_size(total_size)} "
                            f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
                        )
                        sys.stdout.flush()
                print()
                log_success(f"Download complete: {dest_path}")
                return True
        except (requests.exceptions.RequestException, ConnectionError) as e:
            log_error(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            time.sleep(3 * attempt)
    return False

def download_poster_thumbnail(poster_url: str, video_path: str, timeout: int = 20) -> str | None:
    if not poster_url: return None
    thumb_path = video_path + "_thumb.jpg"
    try:
        resp = requests.get(poster_url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(thumb_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
        return thumb_path
    except requests.exceptions.RequestException as e:
        log_warn(f"Poster download failed: {e}")
        return None

def upload_video(file_path, thumb_path, caption, duration, width, height):
    file_size = os.path.getsize(file_path)
    start_time = time.time()
    last_print = [0]
    video_mime = get_video_mimetype(file_path)

    def create_callback(monitor):
        def callback(m):
            now = time.time()
            if now - last_print[0] < 0.3 and m.bytes_read != m.len: return
            last_print[0] = now
            percent = m.bytes_read / m.len * 100
            elapsed = now - start_time
            speed = m.bytes_read / elapsed if elapsed > 0 else 0
            eta = (m.len - m.bytes_read) / speed if speed > 0 else 0
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = "█"*filled + "-"*(bar_len-filled)
            sys.stdout.write(
                f"\r{Fore.MAGENTA}⬆ Uploading{Style.RESET_ALL} [{bar}] "
                f"{percent:5.1f}% | {human_size(m.bytes_read)}/{human_size(m.len)} "
                f"| {human_size(speed)}/s | ETA: {int(eta)}s  "
            )
            sys.stdout.flush()
        return callback

    fields = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "duration": str(duration),
        "width": str(width),
        "height": str(height),
        "supports_streaming": "true", # Mandatory API Flag for Streaming
        "video": (os.path.basename(file_path), open(file_path, "rb"), video_mime),
    }
    if thumb_path and os.path.exists(thumb_path):
        fields["thumb"] = (os.path.basename(thumb_path), open(thumb_path, "rb"), "image/jpeg")

    encoder = MultipartEncoder(fields=fields)
    monitor = MultipartEncoderMonitor(encoder, create_callback(encoder))

    try:
        response = requests.post(
            f"{BOT_API}/sendVideo",
            data=monitor,
            headers={"Content-Type": monitor.content_type},
            timeout=None
        )
        print()
        result = response.json()
        if result.get("ok"):
            log_success(f"Upload verified — message_id: {result['result']['message_id']}")
            return True
        else:
            log_error(f"Upload failed: {result}")
            return False
    except Exception as e:
        print()
        log_error(f"Upload exception: {e}")
        return False

# @title 5. API Fetching, Duplicate Checking & Main Pipeline

SKIP_EXTENSIONS = {".zip", ".rar", ".7z"}

def is_archive_file(url: str, filename: str) -> tuple[bool, str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in SKIP_EXTENSIONS:
        return True, f"extension '{ext}'"
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
        if ct in {
            "application/zip",
            "application/x-zip-compressed",
            "application/x-rar-compressed",
            "application/x-7z-compressed",
        }:
            return True, f"content-type '{ct}'"
    except Exception:
        pass
    return False, ""

def get_remote_file_size(url: str) -> int | None:
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        if resp.headers.get("Content-Length", "").isdigit():
            return int(resp.headers.get("Content-Length"))

        resp = requests.get(url, timeout=15, stream=True, headers={"Range": "bytes=0-0"})
        if resp.headers.get("Content-Range", "").split("/")[-1].isdigit():
            return int(resp.headers.get("Content-Range").split("/")[-1])
    except Exception:
        pass
    return None

def is_within_size_limit(url: str):
    size = get_remote_file_size(url)
    return (False, None) if size is None else (size <= MAX_SIZE_BYTES_NORMAL, size)

def load_seen_links() -> set:
    try:
        if seen_links_col is not None:
            docs = seen_links_col.find({})
            return set(doc.get("url") for doc in docs if doc.get("url"))
    except Exception as e:
        log_warn(f"Error loading seen links from MongoDB: {e}")
    return set()

def mark_seen(link: str, seen: set):
    cleaned = link.strip()
    if not cleaned:
        return
    seen.add(cleaned)
    try:
        if seen_links_col is not None:
            seen_links_col.update_one(
                {"url": cleaned},
                {"$set": {"url": cleaned, "last_updated": datetime.now()}},
                upsert=True
            )
    except Exception as e:
        log_warn(f"Error marking link as seen in MongoDB: {e}")

def extract_links(movie: dict) -> list[dict]:
    raw = movie.get("links")
    if not raw:
        return []
    try:
        groups = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []

    flattened = []
    for group in groups:
        quality_label = group.get("quality", "")
        for link_obj in group.get("links", []):
            if link_obj.get("url"):
                flattened.append({
                    "quality_label": quality_label,
                    "text": link_obj.get("text", ""),
                    "url": link_obj.get("url"),
                })
    return flattened

def run_pipeline(url: str, movie: dict = None) -> tuple[bool, bool]:
    """
    Returns:
        (success: bool, should_mark_seen: bool)
    """
    dest_path = None
    thumb_path = None
    try:
        filename = get_filename_from_headers(url)
        is_archive, reason = is_archive_file(url, filename)
        if is_archive:
            log_warn(f"Skipping {filename}: detected as archive ({reason}).")
            return False, True  # Archive file -> Mark seen immediately

        ok, size_bytes = is_within_size_limit(url)
        if size_bytes is not None and not ok:
            log_warn(f"Skipping {filename}: Size ({human_size(size_bytes)}) exceeds 2GB limit.")
            return False, True  # Mark seen so it's not retried

        if size_bytes is None:
            log_warn(f"Could not verify file size for {filename}. Proceeding with attempt...")

        dest_path = os.path.join(DOWNLOAD_DIR, filename)

        # Remove existing partial file from prior attempt if present
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass

        if not download_file(url, dest_path):
            return False, False  # Download failed

        # Apply FastStart streaming optimization
        dest_path = optimize_video_for_streaming(dest_path)

        # Grab Metadata after optimization / compression
        meta = get_video_metadata(dest_path)
        poster_url = movie.get("poster_url") if movie else None
        thumb_path = download_poster_thumbnail(poster_url, dest_path)

        caption = (
            f"📁 Name: {os.path.basename(dest_path)}\n"
            f"📦 Size: {human_size(meta['size'])}\n"
            f"🎥 Resolution: {meta['width']}×{meta['height']}\n"
            f"⏱ Duration: {format_duration(meta['duration'])}\n"
        )

        success = upload_video(
            dest_path, thumb_path, caption, meta["duration"], meta["width"], meta["height"]
        )

        if success:
            return True, True  # Success -> Mark seen
        return False, False  # Upload failed

    except Exception as e:
        log_warn(f"Pipeline error for {url}: {e}")
        return False, False
    finally:
        # Guarantee cleanup after every attempt
        try:
            if dest_path and os.path.exists(dest_path):
                os.remove(dest_path)
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

def run_pipeline_one_by_one(process_fn=None, delay_seconds: float = 0, max_retries: int = 1):
    seen = load_seen_links()
    if movies_col is not None:
        try:
            total_movies_count = movies_col.count_documents({})
            print(f"Total movies in MongoDB: {total_movies_count}")
        except Exception as e:
            log_warn(f"Error counting movies in MongoDB: {e}")
            return
    else:
        print("Movies collection not available.")
        return

    print("Fetching movies page-wise (starting from page_num 1 upwards) and extracting links...")
    try:
        cursor = movies_col.find({}).sort([("page_num", 1), ("id", 1)])
        all_movies = list(cursor)
    except Exception as e:
        log_warn(f"Error fetching movies from MongoDB: {e}")
        all_movies = []

    unique_pages = set(m.get('page_num') for m in all_movies if m.get('page_num') is not None)
    total_pages_count = len(unique_pages)
    print(f"Total Pages Found: {total_pages_count}")

    all_movie_links = []
    for movie in all_movies:
        for link_info in extract_links(movie):
            all_movie_links.append((movie, link_info))

    total_links_count = len(all_movie_links)
    print(f"Total links found across all movies: {total_links_count}\n")

    batch_size = 1000
    total_processed_count = 0
    total_skipped_count = 0

    for start_idx in range(0, total_links_count, batch_size):
        batch_links = all_movie_links[start_idx:start_idx + batch_size]

        unseen_batch_links = [
            (movie, link_info)
            for movie, link_info in batch_links
            if link_info["url"] not in seen
        ]

        skipped_count = len(batch_links) - len(unseen_batch_links)
        total_skipped_count += skipped_count

        if not unseen_batch_links:
            continue

        for i, (movie, link_info) in enumerate(unseen_batch_links, 1):
            url = link_info["url"]

            if url in seen:
                continue

            print(
                f"[{i}/{len(unseen_batch_links)}] Processing (Page {movie.get('page_num', '?')}): {movie.get('title')} [{link_info.get('quality_label')}]"
            )

            success = False
            should_mark_seen = False

            for attempt in range(1, max_retries + 1):
                try:
                    res = process_fn(movie, link_info) if process_fn else (False, False)

                    if isinstance(res, tuple):
                        success, should_mark_seen = res
                    elif isinstance(res, bool):
                        success, should_mark_seen = res, res
                    else:
                        success, should_mark_seen = False, False

                    if success:
                        mark_seen(url, seen)
                        total_processed_count += 1
                        print("SUCCESS: Uploaded and marked as seen.\n")
                        break

                    if should_mark_seen:
                        mark_seen(url, seen)
                        print("SKIPPED & MARKED SEEN: Archive file.\n")
                        break

                    print(f"Attempt {attempt}/{max_retries} failed.")
                except Exception as e:
                    print(f"Attempt {attempt}/{max_retries} ERROR: {e}")

                if attempt < max_retries:
                    time.sleep(2)

            if not success and not should_mark_seen:
                mark_seen(url, seen)
                print("SKIPPED / FAILED: File exceeded size limit or error. Marked seen to prevent future retries.\n")

            if delay_seconds:
                time.sleep(delay_seconds)

    print(f"\n==============================")
    print(f"PIPELINE SUMMARY")
    print(f"==============================")
    print(f"Total Pages: {total_pages_count}")
    print(f"Total Movies: {total_movies_count}")
    print(f"Total Links Checked: {total_links_count}")
    print(f"Total Already Processed (Skipped): {total_skipped_count}")
    print(f"Total Newly Processed/Uploaded: {total_processed_count}")
    print(f"==============================\n")

def my_download_handler(movie: dict, link_info: dict):
    return run_pipeline(link_info["url"], movie=movie)

# @title 6. Run Execution
run_pipeline_one_by_one(process_fn=my_download_handler, delay_seconds=1.0)


!nohup /content/telegram-bot-api \
  --api-id=22219997 \
  --api-hash=e3840aec1ee4daefa979d3ceeecba323 \
  --local \
  --http-port=8081 \
  > telegram.log 2>&1 &

