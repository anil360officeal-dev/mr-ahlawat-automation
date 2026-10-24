#!/usr/bin/env python3
"""Optional Agnes AI text-to-video B-roll generator for Mr Ahlawat Shorts.
Uses AGNES_API_KEY from the environment. It never uploads to YouTube.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

API_ROOT = "https://apihub.agnes-ai.com"
MODEL = "agnes-video-v2.0"
OUT = Path("output/media/clip_agnes_01.mp4")


def request_json(method, url, key, payload=None, timeout=60):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MrAhlawatShorts/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"Agnes API HTTP {exc.code}: {detail}") from exc


def find_video_url(value):
    if isinstance(value, dict):
        for key in ("video_url", "download_url", "videoUrl", "url"):
            item = value.get(key)
            if isinstance(item, str) and item.startswith(("https://", "http://")):
                if any(ext in item.lower() for ext in (".mp4", ".mov", ".webm")) or key != "url":
                    return item
        for item in value.values():
            found = find_video_url(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_video_url(item)
            if found:
                return found
    return None


def main():
    key = os.environ.get("AGNES_API_KEY", "").strip()
    if not key:
        print("AGNES_VIDEO_SKIPPED: AGNES_API_KEY secret is not configured.")
        return 0

    metadata_path = Path("output/metadata.json")
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    title = str(metadata.get("title", "")).strip()
    desc = str(metadata.get("description", "")).strip()
    # Generic illustrative B-roll only; do not fabricate footage of a real person/event.
    topic = (title or desc or "Indian public-interest news").replace("\n", " ")
    topic = topic[:450]
    prompt = (
        "Create a short cinematic documentary B-roll video for an Indian Hindi news explainer. "
        f"Topic context: {topic}. "
        "Show only illustrative, non-identifiable scenes relevant to the topic: realistic Indian city "
        "streets, public buildings from a distance, people as unidentifiable silhouettes, natural handheld "
        "camera movement, documentary lighting, credible everyday details. Vertical 9:16 composition. "
        "No text, no subtitles, no logos, no flags unless specifically requested, no recognizable politicians, "
        "no fake news footage, no fabricated specific event. 4 to 6 seconds."
    )
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "height": 768,
        "width": 432,
        "num_frames": 97,
        "frame_rate": 16,
    }
    result = request_json("POST", f"{API_ROOT}/v1/videos", key, payload)
    video_id = result.get("video_id") or result.get("id")
    url = find_video_url(result)
    if not url and not video_id:
        raise RuntimeError("Agnes API response contained neither video_id nor a video URL.")
    if not url:
        for attempt in range(36):
            time.sleep(5)
            status = request_json(
                "GET", f"{API_ROOT}/agnesapi?{urllib.parse.urlencode({'video_id': video_id})}", key
            )
            state = str(status.get("status", status.get("state", ""))).lower()
            url = find_video_url(status)
            if url and (state in ("", "success", "succeeded", "completed", "done") or url):
                break
            if state in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Agnes video task failed: {json.dumps(status)[:1000]}")
        if not url:
            raise TimeoutError("Agnes video generation did not return a downloadable video URL in 3 minutes.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "MrAhlawatShorts/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp, OUT.open("wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if not OUT.exists() or OUT.stat().st_size < 10000:
        OUT.unlink(missing_ok=True)
        raise RuntimeError("Agnes returned an empty or suspiciously small video file.")
    print(f"AGNES_VIDEO_READY: {OUT} ({OUT.stat().st_size} bytes)")
    print("AGNES_VIDEO_NOTICE: generated clip is illustrative B-roll, not verified event footage.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("AGNES_VIDEO_WARNING:", str(exc)[:1200])
        # Optional provider must never block the existing preview pipeline.
        raise SystemExit(0)
