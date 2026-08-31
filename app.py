from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from pathlib import Path
from flask_cors import CORS
import yt_dlp

from threading import Semaphore, Thread
import tempfile
import shutil
import os
import re
import time
import uuid
FFMPEG_PATH = shutil.which("ffmpeg") or "/usr/bin"
from collections import defaultdict, deque


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()

app = Flask(__name__)


# =========================================================
# SETTINGS
# =========================================================

# Maximum file size
# Default = 1024 MB = 1 GB

MAX_FILE_SIZE_MB = int(
    os.getenv("MAX_FILE_SIZE_MB", "1024")
)

MAX_FILE_SIZE = (
    MAX_FILE_SIZE_MB * 1024 * 1024
)


# Only ONE download at a time

DOWNLOAD_LIMIT = Semaphore(1)


# Request protection

RATE_LIMIT_REQUESTS = int(
    os.getenv("RATE_LIMIT_REQUESTS", "5")
)

RATE_LIMIT_WINDOW = int(
    os.getenv("RATE_LIMIT_WINDOW", "600")
)


# Same IP must wait 30 seconds

MIN_DOWNLOAD_GAP = int(
    os.getenv("MIN_DOWNLOAD_GAP", "30")
)


# Maximum download time

DOWNLOAD_TIMEOUT = int(
    os.getenv("DOWNLOAD_TIMEOUT", "300")
)


# =========================================================
# STORAGE
# =========================================================

request_history = defaultdict(deque)

jobs = {}

jobs_lock = Semaphore(1)


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# GET CLIENT IP
# =========================================================

def get_client_ip():

    # Cloudflare

    cloudflare_ip = request.headers.get(
        "CF-Connecting-IP"
    )

    if cloudflare_ip:

        return cloudflare_ip.strip()


    # Proxy

    forwarded_ip = request.headers.get(
        "X-Forwarded-For"
    )

    if forwarded_ip:

        return (
            forwarded_ip
            .split(",")[0]
            .strip()
        )


    return (
        request.remote_addr
        or "unknown"
    )


# =========================================================
# RATE LIMIT
# =========================================================

def check_rate_limit(ip):

    now = time.time()

    history = request_history[ip]


    # Remove old requests

    while history and (
        now - history[0]
        > RATE_LIMIT_WINDOW
    ):

        history.popleft()


    # Maximum requests

    if len(history) >= RATE_LIMIT_REQUESTS:

        retry_after = int(
            RATE_LIMIT_WINDOW
            - (now - history[0])
        )

        return False, (
            "Too many download requests. "
            f"Please try again after "
            f"{max(retry_after, 1)} seconds."
        )


    # Minimum gap

    if history:

        time_since_last = (
            now - history[-1]
        )

        if time_since_last < MIN_DOWNLOAD_GAP:

            wait_time = int(
                MIN_DOWNLOAD_GAP
                - time_since_last
            ) + 1

            return False, (
                "Please wait "
                f"{wait_time} seconds "
                "before downloading again."
            )


    history.append(now)

    return True, None


# =========================================================
# YOUTUBE URL VALIDATION
# =========================================================

def is_youtube_url(url):

    pattern = (
        r"^https?://"
        r"(www\.)?"
        r"(youtube\.com/"
        r"(watch\?v=|shorts/|embed/|live/)|"
        r"youtu\.be/)"
    )

    return bool(
        re.match(
            pattern,
            url.strip(),
            re.IGNORECASE
        )
    )


# =========================================================
# FORMAT TIME
# =========================================================

def format_seconds(seconds):

    if seconds is None:

        return "--"


    try:

        seconds = int(seconds)

    except:

        return "--"


    if seconds < 0:

        return "--"


    hours = seconds // 3600

    minutes = (
        seconds % 3600
    ) // 60

    secs = seconds % 60


    if hours > 0:

        return (
            f"{hours}:{minutes:02d}:{secs:02d}"
        )


    return (
        f"{minutes}:{secs:02d}"
    )


# =========================================================
# FORMAT SIZE
# =========================================================

def format_bytes(value):

    if value is None:

        return "--"


    try:

        value = float(value)

    except:

        return "--"


    if value < 1024:

        return (
            f"{value:.0f} B"
        )


    if value < 1024 ** 2:

        return (
            f"{value / 1024:.1f} KB"
        )


    if value < 1024 ** 3:

        return (
            f"{value / (1024 ** 2):.1f} MB"
        )


    return (
        f"{value / (1024 ** 3):.2f} GB"
    )


# =========================================================
# SAFE TITLE
# =========================================================

def make_safe_title(title):

    if not title:

        return "YouTube_Download"


    safe_title = re.sub(
        r"[^a-zA-Z0-9_\- ]",
        "",
        title
    ).strip()


    if not safe_title:

        safe_title = "YouTube_Download"


    return safe_title[:80]


# =========================================================
# UPDATE JOB
# =========================================================

def update_job(job_id, **values):

    with jobs_lock:

        if job_id in jobs:

            jobs[job_id].update(
                values
            )


# =========================================================
# YT-DLP PROGRESS HOOK
# =========================================================

def make_progress_hook(job_id):

    def progress_hook(data):

        try:

            status = data.get(
                "status"
            )


            # -----------------------------------------
            # DOWNLOADING
            # -----------------------------------------

            if status == "downloading":

                downloaded = (
                    data.get(
                        "downloaded_bytes"
                    )
                    or 0
                )


                total = (
                    data.get(
                        "total_bytes"
                    )
                    or data.get(
                        "total_bytes_estimate"
                    )
                    or 0
                )


                if total > 0:

                    percent = (
                        downloaded
                        / total
                        * 100
                    )

                else:

                    percent = 0


                speed = data.get(
                    "speed"
                )


                eta = data.get(
                    "eta"
                )


                update_job(

                    job_id,

                    status="downloading",

                    progress=round(
                        min(
                            max(
                                percent,
                                0
                            ),
                            99.9
                        ),
                        1
                    ),

                    downloaded=format_bytes(
                        downloaded
                    ),

                    total=format_bytes(
                        total
                    ),

                    speed=(
                        format_bytes(speed)
                        + "/s"
                        if speed
                        else "0 MB/s"
                    ),

                    eta=format_seconds(
                        eta
                    )
                )


            # -----------------------------------------
            # PROCESSING / FINISHED
            # -----------------------------------------

            elif status == "finished":

                update_job(

                    job_id,

                    status="processing",

                    progress=99.9,

                    speed="Processing...",

                    eta="Almost done"
                )


        except Exception as error:

            print(
                "PROGRESS ERROR:",
                error
            )


    return progress_hook


# =========================================================
# BACKGROUND DOWNLOAD
# =========================================================

def run_download(
    job_id,
    url,
    download_type,
    temp_dir
):

    start_time = time.time()


    try:

        # =================================================
        # ONLY ONE DOWNLOAD AT A TIME
        # =================================================

        with DOWNLOAD_LIMIT:

            update_job(

                job_id,

                status="queued",

                progress=0,

                downloaded="0 MB",

                total="--",

                speed="Waiting...",

                eta="--"
            )


            # =============================================
            # OUTPUT
            # =============================================

            output_template = str(
                temp_dir
                / "%(id)s.%(ext)s"
            )


            # =============================================
            # VIDEO OPTIONS
            # =============================================

            if download_type == "video":

                options = {

                    "outtmpl":
                        output_template,

                    "noplaylist":
                        True,

                    "quiet":
                        True,

                    "no_warnings":
                        True,

                    "format": "bestvideo+bestaudio/best",
                   
                    "ffmpeg_location": FFMPEG_PATH,
                    "socket_timeout":
                        60,

                    "retries":
                        3,

                    "fragment_retries":
                        3,

                    "restrictfilenames":
                        True,

                    "noprogress":
                        True,

                    "progress_hooks":
                        [
                            make_progress_hook(
                                job_id
                            )
                        ],
                }


            # =============================================
            # AUDIO OPTIONS
            # =============================================

            else:

                options = {

                    "outtmpl":
                        output_template,

                    "noplaylist":
                        True,

                    "quiet":
                        True,

                    "no_warnings":
                        True,

                    "format":
                        "bestaudio/best",
                    "ffmpeg_location": FFMPEG_PATH,
                    "socket_timeout":
                        60,

                    "retries":
                        3,

                    "fragment_retries":
                        3,

                    "restrictfilenames":
                        True,

                    "noprogress":
                        True,

                    "progress_hooks":
                        [
                            make_progress_hook(
                                job_id
                            )
                        ],
                }


            # =============================================
            # START DOWNLOAD
            # =============================================

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True
                )


            # =============================================
            # TIME CHECK
            # =============================================

            elapsed = (
                time.time()
                - start_time
            )


            if elapsed > DOWNLOAD_TIMEOUT:

                raise RuntimeError(
                    "Download took too long."
                )


        # =================================================
        # FIND FILE
        # =================================================

        if download_type == "video":

            allowed_extensions = {

                ".mp4",
                ".webm",
                ".mkv"

            }

        else:

            allowed_extensions = {

                ".m4a",
                ".webm",
                ".opus",
                ".mp3"

            }


        downloaded_files = [

            file

            for file
            in temp_dir.iterdir()

            if (

                file.is_file()

                and

                file.suffix.lower()
                in allowed_extensions

            )

        ]


        if not downloaded_files:

            raise RuntimeError(
                "Downloaded file was not created."
            )


        downloaded_file = (
            downloaded_files[0]
        )


        # =================================================
        # FILE SIZE CHECK
        # =================================================

        file_size = (
            downloaded_file
            .stat()
            .st_size
        )


        if file_size > MAX_FILE_SIZE:

            raise RuntimeError(

                "File is larger than "
                f"{MAX_FILE_SIZE_MB} MB."
            )


        # =================================================
        # TITLE
        # =================================================

        title = (
            info.get("title")
            or "YouTube Download"
        )


        safe_title = make_safe_title(
            title
        )


        # =================================================
        # EXTENSION
        # =================================================

        extension = (
            downloaded_file
            .suffix
            .lower()
            .replace(".", "")
        )


        download_name = (
            f"{safe_title}.{extension}"
        )


        # =================================================
        # MIME TYPE
        # =================================================

        if extension == "mp4":

            mimetype = "video/mp4"

        elif extension == "webm":

            if download_type == "video":

                mimetype = "video/webm"

            else:

                mimetype = "audio/webm"

        elif extension == "m4a":

            mimetype = "audio/mp4"

        elif extension == "opus":

            mimetype = "audio/ogg"

        elif extension == "mp3":

            mimetype = "audio/mpeg"

        elif extension == "mkv":

            mimetype = "video/x-matroska"

        else:

            mimetype = (
                "application/octet-stream"
            )


        # =================================================
        # SAVE JOB RESULT
        # =================================================

        update_job(

            job_id,

            status="ready",

            progress=100,

            downloaded=format_bytes(
                file_size
            ),

            total=format_bytes(
                file_size
            ),

            speed="Done",

            eta="Completed",

            file_path=str(
                downloaded_file
            ),

            download_name=download_name,

            mimetype=mimetype
        )


        print(
            f"DOWNLOAD COMPLETE: {job_id}"
        )


    except Exception as error:

        print(
            "DOWNLOAD ERROR:",
            error
        )


        update_job(

            job_id,

            status="error",

            progress=0,

            error=(
                "Download nahi ho paya. "
                "Video publicly accessible "
                "honi chahiye aur URL valid "
                "hona chahiye."
            )
        )


        # Cleanup on error

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# START DOWNLOAD API
# =========================================================

@app.route(
    "/api/download",
    methods=["POST"]
)

def start_download():

    # =====================================================
    # REQUEST SIZE
    # =====================================================

    if request.content_length:

        if request.content_length > (
            1024 * 1024
        ):

            return jsonify({

                "success":
                    False,

                "error":
                    "Request too large."

            }), 413


    # =====================================================
    # READ JSON
    # =====================================================

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    url = (
        data.get("url")
        or ""
    ).strip()


    download_type = (
        data.get("type")
        or "video"
    ).lower().strip()


    # =====================================================
    # URL REQUIRED
    # =====================================================

    if not url:

        return jsonify({

            "success":
                False,

            "error":
                "YouTube URL required."

        }), 400


    # =====================================================
    # URL VALIDATION
    # =====================================================

    if not is_youtube_url(url):

        return jsonify({

            "success":
                False,

            "error":
                "Please enter a valid YouTube URL."

        }), 400


    # =====================================================
    # TYPE VALIDATION
    # =====================================================

    if download_type not in {

        "video",
        "audio"

    }:

        return jsonify({

            "success":
                False,

            "error":
                "Invalid download type."

        }), 400


    # =====================================================
    # RATE LIMIT
    # =====================================================

    client_ip = get_client_ip()


    allowed, error_message = (
        check_rate_limit(
            client_ip
        )
    )


    if not allowed:

        return jsonify({

            "success":
                False,

            "error":
                error_message

        }), 429


    # =====================================================
    # CREATE JOB
    # =====================================================

    job_id = str(
        uuid.uuid4()
    )


    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=
                "youtube_downloader_"
        )
    )


    # =====================================================
    # INITIAL JOB
    # =====================================================

    with jobs_lock:

        jobs[job_id] = {

            "status":
                "queued",

            "progress":
                0,

            "downloaded":
                "0 MB",

            "total":
                "--",

            "speed":
                "Waiting...",

            "eta":
                "--",

            "file_path":
                None,

            "download_name":
                None,

            "mimetype":
                None,

            "error":
                None,

            "created":
                time.time()
        }


    # =====================================================
    # START THREAD
    # =====================================================

    worker = Thread(

        target=run_download,

        args=(

            job_id,
            url,
            download_type,
            temp_dir

        ),

        daemon=True
    )


    worker.start()


    # =====================================================
    # RESPONSE
    # =====================================================

    return jsonify({

        "success":
            True,

        "job_id":
            job_id,

        "message":
            "Download started."

    })


# =========================================================
# PROGRESS API
# =========================================================

@app.route(
    "/api/progress/<job_id>",
    methods=["GET"]
)

def download_progress(job_id):

    with jobs_lock:

        job = jobs.get(
            job_id
        )


    if not job:

        return jsonify({

            "success":
                False,

            "error":
                "Download job not found."

        }), 404


    response = {

        "success":
            True,

        "status":
            job.get(
                "status",
                "queued"
            ),

        "progress":
            job.get(
                "progress",
                0
            ),

        "downloaded":
            job.get(
                "downloaded",
                "0 MB"
            ),

        "total":
            job.get(
                "total",
                "--"
            ),

        "speed":
            job.get(
                "speed",
                "0 MB/s"
            ),

        "eta":
            job.get(
                "eta",
                "--"
            )
    }


    if job.get("error"):

        response["error"] = (
            job["error"]
        )


    return jsonify(
        response
    )


# =========================================================
# DOWNLOAD FILE API
# =========================================================

@app.route(
    "/api/file/<job_id>",
    methods=["GET"]
)

def download_file(job_id):

    with jobs_lock:

        job = jobs.get(
            job_id
        )


    if not job:

        return jsonify({

            "success":
                False,

            "error":
                "Download job not found."

        }), 404


    if job.get("status") != "ready":

        return jsonify({

            "success":
                False,

            "error":
                "File is not ready yet."

        }), 400


    file_path = job.get(
        "file_path"
    )


    if not file_path:

        return jsonify({

            "success":
                False,

            "error":
                "File not found."

        }), 404


    file = Path(
        file_path
    )


    if not file.exists():

        return jsonify({

            "success":
                False,

            "error":
                "Downloaded file no longer exists."

        }), 404


    response = send_file(

        file,

        mimetype=job.get(
            "mimetype",
            "application/octet-stream"
        ),

        as_attachment=True,

        download_name=job.get(
            "download_name",
            file.name
        )
    )


    # =====================================================
    # CLEANUP
    # =====================================================

    @response.call_on_close
    def cleanup():

        try:

            shutil.rmtree(
                file.parent,
                ignore_errors=True
            )

        except Exception:

            pass


        with jobs_lock:

            jobs.pop(
                job_id,
                None
            )


    return response


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route(
    "/health"
)

def health():

    return jsonify({

        "status":
            "ok"

    })


# =========================================================
# CLEAN OLD JOBS
# =========================================================

def cleanup_old_jobs():

    while True:

        time.sleep(
            600
        )


        now = time.time()


        old_jobs = []


        with jobs_lock:

            for job_id, job in list(
                jobs.items()
            ):

                created = job.get(
                    "created",
                    now
                )


                if (
                    now - created
                    > 1800
                ):

                    old_jobs.append(
                        (
                            job_id,
                            job
                        )
                    )


            for job_id, job in old_jobs:

                jobs.pop(
                    job_id,
                    None
                )


        # Remove old files

        for _, job in old_jobs:

            file_path = job.get(
                "file_path"
            )


            if file_path:

                try:

                    shutil.rmtree(
                        Path(
                            file_path
                        ).parent,
                        ignore_errors=True
                    )

                except Exception:

                    pass


# =========================================================
# START CLEANUP THREAD
# =========================================================

cleanup_thread = Thread(

    target=cleanup_old_jobs,

    daemon=True
)

cleanup_thread.start()


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    print()

    print(
        "======================================"
    )

    print(
        " YouTube Video & Audio Downloader"
    )

    print(
        "======================================"
    )

    print()

    print(
        "Maximum file size:"
    )

    print(
        f"{MAX_FILE_SIZE_MB} MB"
    )

    print()

    print(
        "Maximum simultaneous downloads:"
    )

    print("1")

    print()

    print(
        "Request limit:"
    )

    print(
        f"{RATE_LIMIT_REQUESTS} requests/"
        f"{RATE_LIMIT_WINDOW // 60} minutes"
    )

    print()

    print(
        "Minimum download gap:"
    )

    print(
        f"{MIN_DOWNLOAD_GAP} seconds"
    )

    print()

    print(
        "Open:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False
    )
