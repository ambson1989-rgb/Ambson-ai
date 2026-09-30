"""
Assembles a Reel from beats (still image + matching narration audio) using
ffmpeg: Ken Burns zoom, burned-in caption, then concat to one vertical video.
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


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}):\n{err}")


def build_beat_clip(image_path: str, audio_path: str, caption: str, out_path: str) -> str:
    duration = _probe_duration(audio_path)
    frames = max(int(duration * FPS), 1)

    caption_path = out_path + ".caption.txt"
    with open(caption_path, "w") as f:
        f.write(_wrap_caption(caption))

    # Escape path for drawtext filter (colons/special chars)
    font = FONT_PATH.replace("\\", "/").replace(":", "\\:")
    cap = caption_path.replace("\\", "/").replace(":", "\\:")

    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"zoompan=z='min(zoom+0.0015,1.3)':d={frames}:s={W}x{H}:fps={FPS},"
        f"format=yuv420p,"
        f"drawtext=fontfile={font}:textfile={cap}:fontsize=58:"
        f"fontcolor=white:line_spacing=14:box=1:boxcolor=black@0.55:boxborderw=24:"
        f"x=(w-text_w)/2:y=h-th-180"
    )

    try:
        _run_ffmpeg(
            [
                "ffmpeg", "-y", "-loop", "1", "-t", str(duration), "-i", image_path,
                "-i", audio_path, "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-shortest", out_path,
            ]
        )
    finally:
        if os.path.exists(caption_path):
            os.remove(caption_path)

    return out_path


def concat_clips(clip_paths: list[str], out_path: str) -> str:
    list_path = out_path + ".list.txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path]
        )
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

    return out_path
