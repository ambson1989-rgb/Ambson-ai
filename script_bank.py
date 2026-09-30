"""
Fact-checked scripts, broken into beats -- each beat is one narration line
plus a matching image prompt. pick_script() rotates through SCRIPTS, one per
calendar day.

Niche: history / ancient engineering / cosmic mysteries / hard science discoveries.
Ask for a refill once you cycle through these — new batches should get the same
fact-check pass.
"""

import json
import os
from datetime import date

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

SCRIPTS = [
    {
        "topic": "The Antikythera mechanism — the 2,000-year-old Greek analog computer",
        "beats": [
            {
                "narration": "This 2,000-year-old machine shouldn't exist.",
                "image_prompt": (
                    "cinematic photo of a corroded ancient bronze mechanical device "
                    "with intricate gears, museum lighting, dark background, "
                    "mysterious atmosphere, highly detailed, no people"
                ),
            },
            {
                "narration": (
                    "In 1901, sponge divers found a corroded block of bronze "
                    "off the Greek island of Antikythera."
                ),
                "image_prompt": (
                    "cinematic underwater scene, ancient shipwreck on Mediterranean "
                    "seabed, sunlight rays through water, bronze artifact fragment, "
                    "no people, moody atmospheric lighting"
                ),
            },
            {
                "narration": (
                    "Inside were more than 30 hand-driven bronze gears, modeling "
                    "the cycles of the Moon, Sun, and known planets."
                ),
                "image_prompt": (
                    "extreme close-up of intricate ancient bronze gear mechanism, "
                    "cosmic diagram of sun moon and planets etched into metal, "
                    "warm golden light, highly detailed engineering, no people"
                ),
            },
            {
                "narration": (
                    "Nothing this mechanically complex is known from before "
                    "the fourteenth century."
                ),
                "image_prompt": (
                    "dramatic split composition, ancient bronze clockwork gears "
                    "contrasted with a medieval European clock tower, mysterious "
                    "dark cinematic lighting, no people"
                ),
            },
            {
                "narration": "Who built it is still unconfirmed.",
                "image_prompt": (
                    "ancient Greek ruins silhouette at dusk under a starry night "
                    "sky, contemplative and mysterious mood, wide cinematic shot, "
                    "no people"
                ),
            },
        ],
    },
    {
        "topic": "Tesla's Wardenclyffe Tower and why J.P. Morgan pulled funding",
        "beats": [
            {
                "narration": "Tesla's tower was meant to talk across the Atlantic.",
                "image_prompt": (
                    "cinematic photo of a tall early 1900s wooden and steel "
                    "wireless transmission tower against a dramatic sky, sepia "
                    "toned, atmospheric lighting, no people"
                ),
            },
            {
                "narration": (
                    "In 1901, J.P. Morgan invested $150,000 in it — the aim was "
                    "sending messages across the ocean without cables."
                ),
                "image_prompt": (
                    "vintage early 20th century laboratory with wireless "
                    "transmission equipment, glowing electrical coils, dramatic "
                    "sepia cinematic lighting, no people"
                ),
            },
            {
                "narration": (
                    "When Tesla wanted to expand toward wireless power, Morgan "
                    "refused more funding — the project was abandoned in 1906, "
                    "and the tower was demolished for scrap in 1917."
                ),
                "image_prompt": (
                    "abandoned decaying wooden transmission tower at dusk, "
                    "overgrown lot, melancholic cinematic lighting, no people"
                ),
            },
            {
                "narration": (
                    "The popular 'free energy for the world' story is disputed "
                    "— one historian says Tesla never planned free energy."
                ),
                "image_prompt": (
                    "old sepia toned newspaper clippings and blueprint sketches "
                    "of an electrical tower scattered on a wooden desk, dramatic "
                    "side lighting, no people"
                ),
            },
        ],
    },
    {
        "topic": "The pigeon-droppings discovery of the cosmic microwave background",
        "beats": [
            {
                "narration": "They cleaned pigeon droppings... and heard the Big Bang.",
                "image_prompt": (
                    "cinematic photo of a large 1960s horn-shaped radio antenna "
                    "against a starry night sky, dramatic wide shot, no people"
                ),
            },
            {
                "narration": (
                    "In 1964, Bell Labs researchers picked up a steady hiss "
                    "from every part of the sky."
                ),
                "image_prompt": (
                    "vintage 1960s scientific laboratory control room with "
                    "analog dials and oscilloscope screens, warm dramatic "
                    "lighting, no people"
                ),
            },
            {
                "narration": (
                    "They checked for city interference and cleaned out "
                    "nesting pigeons, but the noise stayed."
                ),
                "image_prompt": (
                    "close-up of a large metal horn antenna structure, birds "
                    "flying away, moody documentary style lighting, no people"
                ),
            },
            {
                "narration": (
                    "It was leftover radiation from the universe's early days "
                    "— a discovery that earned the 1978 Nobel Prize in Physics."
                ),
                "image_prompt": (
                    "epic cosmic scene of the early universe, glowing radiation "
                    "background, stars and nebula, deep space cinematic wide shot"
                ),
            },
        ],
    },
    {
        "topic": "The Baghdad Battery — a 2,000-year-old clay jar that could make electricity",
        "beats": [
            {
                "narration": "A 2,000-year-old clay jar that might have made electricity.",
                "image_prompt": (
                    "ancient clay jar with copper cylinder inside, museum display "
                    "lighting, dark background, mysterious archaeological artifact, "
                    "highly detailed, no people"
                ),
            },
            {
                "narration": (
                    "Found near Baghdad and dated to the Parthian or Sasanian period, "
                    "it held a copper cylinder and an iron rod."
                ),
                "image_prompt": (
                    "cutaway illustration of an ancient clay vessel containing a "
                    "copper tube and iron rod, technical archaeological style, "
                    "warm lighting, no people"
                ),
            },
            {
                "narration": (
                    "Filled with an acidic liquid, similar jars can produce a small "
                    "voltage — enough for electroplating in modern tests."
                ),
                "image_prompt": (
                    "close-up of green copper corrosion and iron metal, scientific "
                    "macro photography, dramatic side light, no people"
                ),
            },
            {
                "narration": (
                    "Whether ancient people used it that way is still debated — "
                    "no texts describe it as a battery."
                ),
                "image_prompt": (
                    "ancient Mesopotamian ruins at sunset, dusty atmosphere, "
                    "cinematic wide shot, contemplative mood, no people"
                ),
            },
        ],
    },
    {
        "topic": "Voynich Manuscript — the book no one can read",
        "beats": [
            {
                "narration": "A 600-year-old book written in a language no one can read.",
                "image_prompt": (
                    "ancient mysterious manuscript pages with unknown script and "
                    "strange botanical drawings, parchment texture, museum lighting, "
                    "no people"
                ),
            },
            {
                "narration": (
                    "The Voynich Manuscript appeared in recorded history in the "
                    "1600s and is carbon-dated to the early 1400s."
                ),
                "image_prompt": (
                    "weathered medieval parchment codex on a wooden table, candlelight, "
                    "dust particles in air, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "It is filled with unknown script, odd plants, astronomical "
                    "diagrams, and naked figures in green baths."
                ),
                "image_prompt": (
                    "close-up of bizarre medieval botanical illustration on aged "
                    "parchment, strange unknown plants, muted colors, no people"
                ),
            },
            {
                "narration": (
                    "Cryptographers, historians, and AI researchers have all tried. "
                    "It remains unsolved."
                ),
                "image_prompt": (
                    "dark library shelves filled with ancient books, single beam of "
                    "light on an open undeciphered manuscript, mysterious atmosphere, "
                    "no people"
                ),
            },
        ],
    },
    {
        "topic": "The Great Pyramid's precision — and the gaps in the record",
        "beats": [
            {
                "narration": "The Great Pyramid is aligned to true north within a fraction of a degree.",
                "image_prompt": (
                    "Great Pyramid of Giza at dawn, golden light, vast desert, "
                    "cinematic wide shot, dramatic sky, no people"
                ),
            },
            {
                "narration": (
                    "Built more than 4,500 years ago, it contains roughly 2.3 million "
                    "stone blocks, some weighing over 40 tons."
                ),
                "image_prompt": (
                    "massive ancient limestone blocks stacked in a pyramid structure, "
                    "close-up texture of weathered stone, warm desert light, no people"
                ),
            },
            {
                "narration": (
                    "How the heaviest stones were raised is still not fully settled — "
                    "ramps, levers, and internal systems are all proposed."
                ),
                "image_prompt": (
                    "artistic reconstruction of ancient Egyptian construction ramps "
                    "beside a rising pyramid, soft documentary light, no people"
                ),
            },
            {
                "narration": (
                    "What is clear: the builders left almost no written explanation "
                    "of the method."
                ),
                "image_prompt": (
                    "empty desert plateau with the Giza pyramids in silhouette under "
                    "stars, contemplative night sky, cinematic, no people"
                ),
            },
        ],
    },
    {
        "topic": "Ötzi the Iceman — a 5,300-year-old murder mystery",
        "beats": [
            {
                "narration": "In 1991, hikers found a body melting out of an Alpine glacier.",
                "image_prompt": (
                    "high alpine glacier landscape, icy blue tones, misty peaks, "
                    "cinematic documentary style, no people"
                ),
            },
            {
                "narration": (
                    "Ötzi lived about 5,300 years ago. His gear included a copper axe, "
                    "a bow, and a quiver of arrows."
                ),
                "image_prompt": (
                    "ancient copper axe and wooden bow on stone, prehistoric tools, "
                    "museum-style dramatic lighting, no people"
                ),
            },
            {
                "narration": (
                    "A flint arrowhead was lodged in his shoulder. He had defensive "
                    "wounds on his hands."
                ),
                "image_prompt": (
                    "close-up of a prehistoric flint arrowhead, sharp edges, dark "
                    "moody lighting, forensic documentary style, no people"
                ),
            },
            {
                "narration": (
                    "He likely died from the arrow wound — one of the oldest known "
                    "forensic murder cases."
                ),
                "image_prompt": (
                    "snowy alpine pass at dusk, lonely and cold atmosphere, "
                    "cinematic wide shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "The Library of Alexandria — what was actually lost",
        "beats": [
            {
                "narration": "The Library of Alexandria is often called the greatest loss in history.",
                "image_prompt": (
                    "grand ancient Hellenistic library interior with scrolls and "
                    "columns, warm golden light, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "It was part of a research institution in Ptolemaic Egypt, "
                    "drawing scholars from across the Mediterranean."
                ),
                "image_prompt": (
                    "ancient Alexandria harbor with lighthouse silhouette, classical "
                    "architecture, sunset over the sea, no people"
                ),
            },
            {
                "narration": (
                    "There was no single dramatic fire that wiped everything out. "
                    "Decline happened over centuries."
                ),
                "image_prompt": (
                    "scattered ancient scrolls and ash on stone floor, dim light, "
                    "melancholic atmosphere, no people"
                ),
            },
            {
                "narration": (
                    "What disappeared was not one catalogue of wonders — but centuries "
                    "of accumulated knowledge, piece by piece."
                ),
                "image_prompt": (
                    "empty classical ruins at twilight, broken columns, reflective "
                    "mood, cinematic wide shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "Pulsars — the cosmic lighthouses that almost weren't believed",
        "beats": [
            {
                "narration": "In 1967, a graduate student found a signal that pulsed every 1.3 seconds.",
                "image_prompt": (
                    "1960s radio telescope array under a clear night sky, documentary "
                    "style, dramatic lighting, no people"
                ),
            },
            {
                "narration": (
                    "Jocelyn Bell Burnell and her advisor first joked it might be "
                    "little green men — then ruled that out."
                ),
                "image_prompt": (
                    "vintage radio astronomy chart with regular pulse spikes on paper, "
                    "scientific instrument aesthetic, no people"
                ),
            },
            {
                "narration": (
                    "It was a pulsar: a rapidly spinning neutron star sweeping a beam "
                    "of radio waves past Earth."
                ),
                "image_prompt": (
                    "artist concept of a neutron star pulsar emitting twin beams of "
                    "radiation in deep space, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "The 1974 Nobel Prize went to her supervisor. Bell Burnell was "
                    "left off the prize — a decision still widely criticized."
                ),
                "image_prompt": (
                    "deep space nebula with a bright pulsing stellar object, epic "
                    "cosmic wide shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "The Tunguska event — the day the sky exploded over Siberia",
        "beats": [
            {
                "narration": "In 1908, something exploded over Siberia with the force of a large nuclear bomb.",
                "image_prompt": (
                    "vast Siberian taiga forest at dawn, flattened trees in a radial "
                    "pattern, cinematic aerial view, no people"
                ),
            },
            {
                "narration": (
                    "Trees were flattened across roughly 2,000 square kilometers. "
                    "No impact crater was found."
                ),
                "image_prompt": (
                    "endless flattened forest from above, scorched and broken trunks, "
                    "moody documentary lighting, no people"
                ),
            },
            {
                "narration": (
                    "The leading explanation is an airburst from a stony asteroid or "
                    "comet fragment that never hit the ground intact."
                ),
                "image_prompt": (
                    "bright fireball streaking through the upper atmosphere over a "
                    "dark forest, dramatic sky, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "Had it happened over a city, the death toll would have been "
                    "catastrophic."
                ),
                "image_prompt": (
                    "empty snowy Siberian landscape under a strange glowing sky, "
                    "ominous and quiet, wide cinematic shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "Roman concrete — why some ancient harbors still stand",
        "beats": [
            {
                "narration": "Some Roman harbors have survived 2,000 years in seawater.",
                "image_prompt": (
                    "ancient Roman concrete pier extending into blue Mediterranean "
                    "water, weathered but intact, sunny day, no people"
                ),
            },
            {
                "narration": (
                    "Romans mixed lime and volcanic ash. Seawater triggered a chemical "
                    "reaction that strengthened the material over time."
                ),
                "image_prompt": (
                    "close-up of porous ancient concrete with crystals, scientific "
                    "macro photography, textured surface, no people"
                ),
            },
            {
                "narration": (
                    "Modern concrete often crumbles in decades under the same "
                    "conditions."
                ),
                "image_prompt": (
                    "cracked modern concrete seawall versus intact ancient stone "
                    "structure nearby, contrast composition, no people"
                ),
            },
            {
                "narration": (
                    "Researchers are still studying Roman recipes to improve "
                    "today's materials."
                ),
                "image_prompt": (
                    "archaeological ruins of a Roman port at sunset, golden light "
                    "on stone, calm sea, cinematic, no people"
                ),
            },
        ],
    },
    {
        "topic": "The Pioneer anomaly — when spacecraft drifted off course",
        "beats": [
            {
                "narration": "Pioneer 10 and 11 drifted slightly off their predicted paths.",
                "image_prompt": (
                    "vintage 1970s spacecraft in deep space, golden antenna dish, "
                    "stars in background, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "For years, physicists wondered if new physics was needed to "
                    "explain the tiny extra acceleration toward the Sun."
                ),
                "image_prompt": (
                    "scientific equation sketches and spacecraft trajectory plots on "
                    "paper, dramatic desk lighting, no people"
                ),
            },
            {
                "narration": (
                    "The leading explanation today is heat recoiling unevenly from "
                    "the spacecraft itself — not new gravity."
                ),
                "image_prompt": (
                    "spacecraft thermal radiation visualization in deep space, subtle "
                    "glow, technical cutaway style, no people"
                ),
            },
            {
                "narration": (
                    "A mystery that looked revolutionary was solved by careful "
                    "engineering physics."
                ),
                "image_prompt": (
                    "distant probe leaving the solar system, pale sunlight, vast "
                    "empty space, contemplative wide shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "Gobekli Tepe — temples older than agriculture",
        "beats": [
            {
                "narration": "These stone circles were built before farming was widespread.",
                "image_prompt": (
                    "massive T-shaped stone pillars at Gobekli Tepe, archaeological "
                    "site, warm Turkish sunlight, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "Gobekli Tepe in modern Turkey dates to roughly 11,000 years ago "
                    "— older than Stonehenge by millennia."
                ),
                "image_prompt": (
                    "close-up of carved animal reliefs on ancient limestone pillars, "
                    "detailed stone texture, dramatic side light, no people"
                ),
            },
            {
                "narration": (
                    "Hunter-gatherers organized large-scale construction long before "
                    "cities or writing."
                ),
                "image_prompt": (
                    "wide view of excavated stone enclosures on a dry hill, "
                    "archaeological atmosphere, no people"
                ),
            },
            {
                "narration": (
                    "It forced historians to rethink which came first: complex "
                    "society, or farming."
                ),
                "image_prompt": (
                    "Gobekli Tepe at sunset, pillars silhouetted against orange sky, "
                    "mysterious and ancient mood, no people"
                ),
            },
        ],
    },
    {
        "topic": "The sabre-toothed black hole at the center of the Milky Way",
        "beats": [
            {
                "narration": "At the center of our galaxy sits a black hole four million times the mass of the Sun.",
                "image_prompt": (
                    "artist concept of Sagittarius A black hole with glowing accretion "
                    "disk, stars orbiting, deep space cinematic, no people"
                ),
            },
            {
                "narration": (
                    "Astronomers tracked stars whipping around an invisible point at "
                    "enormous speeds."
                ),
                "image_prompt": (
                    "star trails orbiting a dark central void in the galactic center, "
                    "scientific visualization style, no people"
                ),
            },
            {
                "narration": (
                    "In 2022, the Event Horizon Telescope released an image of its "
                    "shadow — a dark silhouette ringed by glowing gas."
                ),
                "image_prompt": (
                    "black hole shadow with orange photon ring, Event Horizon "
                    "Telescope style image, cosmic background, no people"
                ),
            },
            {
                "narration": (
                    "You cannot see it with your eyes — but its gravity shapes the "
                    "heart of the Milky Way."
                ),
                "image_prompt": (
                    "Milky Way galactic center dense star field, dramatic dust lanes, "
                    "epic wide cosmic shot, no people"
                ),
            },
        ],
    },
    {
        "topic": "Greek fire — the medieval superweapon that burned on water",
        "beats": [
            {
                "narration": "Medieval Byzantium had a weapon that burned even on water.",
                "image_prompt": (
                    "Byzantine warship on dark sea with jets of flame, dramatic night "
                    "battle atmosphere, cinematic, no people"
                ),
            },
            {
                "narration": (
                    "Greek fire was projected through siphons onto enemy ships. "
                    "Water did not extinguish it."
                ),
                "image_prompt": (
                    "close-up of ancient bronze flame siphon nozzle with fire, "
                    "dramatic sparks, dark background, no people"
                ),
            },
            {
                "narration": (
                    "Its exact recipe was a state secret. It was lost when the "
                    "empire declined."
                ),
                "image_prompt": (
                    "ancient sealed scrolls and laboratory vessels on a stone table, "
                    "candlelight, mysterious mood, no people"
                ),
            },
            {
                "narration": (
                    "Historians still debate the formula — petroleum, resin, and "
                    "quicklime are common guesses."
                ),
                "image_prompt": (
                    "burning oil on dark water surface at night, intense flames "
                    "reflected, cinematic, no people"
                ),
            },
        ],
    },
]


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_index": -1, "last_run_date": None}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def pick_script() -> dict:
    """Rotates through SCRIPTS, one per calendar day, wrapping around."""
    state = _load_state()
    today = date.today().isoformat()

    if state["last_run_date"] == today:
        return SCRIPTS[state["last_index"] % len(SCRIPTS)]

    next_index = (state["last_index"] + 1) % len(SCRIPTS)
    _save_state({"last_index": next_index, "last_run_date": today})
    return SCRIPTS[next_index]
