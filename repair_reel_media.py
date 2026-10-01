"""Re-render one already approved reel using the current corrected on-screen contact line."""
import json
import random
from datetime import date
from pathlib import Path

import generate_daily_reels as g


def main():
    marker = Path(".repair-reel-now")
    reel_id = marker.read_text(encoding="utf-8").strip()
    data = json.loads(g.MANIFEST.read_text(encoding="utf-8"))
    item = next((r for r in data["reels"] if r.get("id") == reel_id), None)
    if item is None:
        raise SystemExit(f"Unknown reel id: {reel_id}")
    prefix = "characzone-"
    date_part, slot = reel_id[len(prefix):].rsplit("-", 1)
    day = date.fromisoformat(date_part)
    seed = int(day.strftime("%Y%m%d")) * 10 + (1 if slot == "am" else 2)

    # Keep the exact source photo order already approved for this reel.
    selected = [g.ASSETS / name for name in item["source_images"]]
    if len(selected) != 9 or any(not path.is_file() for path in selected):
        raise RuntimeError("The reel must have nine available approved source photos")

    # Recreate the generator's title choices for this date.
    rng = random.Random(seed)
    sources = g.photos()
    for _ in range(2):
        block = sources[:]
        rng.shuffle(block)
    copy = g.COPY[:]
    rng.shuffle(copy)
    titles = [rng.choice(g.HOOKS)] + [copy[i] for i in range(1, 9)]

    theme = g.THEMES[seed % len(g.THEMES)]
    work = g.ROOT / "build" / f"{reel_id}-corrected"
    work.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, photo in enumerate(selected):
        frame = work / f"scene-{i:02d}.jpg"
        g.scene(photo, frame, titles[i], theme, i, (seed + i) % 6)
        frames.append(frame)

    soundtrack = work / "music.wav"
    g.music(soundtrack, len(frames) * g.SCENE_SECONDS + 0.5, seed)
    output = g.ROOT / f"{reel_id}-corrected.mp4"
    g.encode(frames, soundtrack, output, seed)

    item["video_url"] = (
        f"https://raw.githubusercontent.com/canakard1000/characzone-auto-reels/main/{output.name}"
    )
    g.MANIFEST.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Re-rendered {reel_id} as {output.name}")
    print("On-screen contact: 가챠머신 창업상담 010-2876-8553")


if __name__ == "__main__":
    main()
