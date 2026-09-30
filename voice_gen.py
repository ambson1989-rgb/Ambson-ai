"""
Free narration via edge-tts -- Microsoft Edge's online text-to-speech,
no API key required. The library is async; wrapped here as a plain
function since the rest of the pipeline is sync.
"""

import asyncio
import edge_tts

# Calm, documentary-style voice -- fits the "history/cosmic mystery" tone.
# Run `edge-tts --list-voices` for the full catalog if you want to swap it.
DEFAULT_VOICE = "en-US-AndrewNeural"


async def _synthesize(text: str, out_path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def generate_narration(text: str, out_path: str, voice: str = DEFAULT_VOICE) -> str:
    asyncio.run(_synthesize(text, out_path, voice))
    return out_path
