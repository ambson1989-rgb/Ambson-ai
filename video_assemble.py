"""
Assembles a Reel from beats (still image + matching narration audio) using
ffmpeg: a slow Ken Burns pan/zoom on each still, timed exactly to that beat's
narration length, with a burned-in caption -- then all beats concatenate
into one continuous vertical (1080x1920) video.

The ffmpeg pipeline itself (this file) was built and verified against
placeholder image/audio inputs during development -- resolution, duration,
caption wrapping and legibility all confirmed working. The images and audio
that feed it (image_gen.py, voice_gen.py) are separate, real network calls
that couldn't be tested end-to-end in that same environment -- worth a
manual test run before trusting the daily schedule.
"""

import os
import subprocess
import textwrap

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "Montserrat-Bold.ttf")
W, H, FPS = 1080, 1920, 30


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _wrap_caption(text: str, width_chars: int = 28) -> str:
    return "\n".join(textwrap.wrap(text, width=width_chars))


def build_beat_clip(image_path: str, audio_path: str, caption: str, out_path: str) -> str:
    """One beat = one still image, Ken-Burns-animated for exactly as long as
    its narration audio runs, with that narration's text burned in as a
    caption."""
    duration = _probe_duration(audio_path)
    frames = max(int(duration * FPS), 1)

    caption_path = out_path + ".caption.txt"
    with open(caption_path, "w") as f:
        f.write(_wrap_caption(caption))

    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"zoompan=z='min(zoom+0.0015,1.3)':d={frames}:s={W}x{H}:fps={FPS},"
        f"format=yuv420p,"
        f"drawtext=fontfile={FONT_PATH}:textfile={caption_path}:fontsize=58:"
        f"fontcolor=white:line_spacing=14:box=1:boxcolor=black@0.55:boxborderw=24:"
        f"x=(w-text_w)/2:y=h-th-180"
    )

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-t", str(duration), "-i", image_path,
                "-i", audio_path, "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-shortest", out_path,
            ],
            check=True, capture_output=True, text=True,
        )
    finally:
        if os.path.exists(caption_path):
            os.remove(caption_path)

    return out_path


def concat_clips(clip_paths: list[str], out_path: str) -> str:
    """Joins beat clips (already same resolution/codec/fps) into one file."""
    list_path = out_path + ".list.txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path],
            check=True, capture_output=True, text=True,
        )
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

    return out_path
