import asyncio
import io
import json
from pathlib import Path
from collections.abc import AsyncIterator

from ..hud import Hud
from ..models import HoleChangeEvent, PreShotEvent, Shot, ShotEvent


def load_jpeg(path: str | None, max_width: int = 1024) -> bytes | None:
    """A replay's screenshot as JPEG bytes, or None when it isn't on disk (the GSPro frames are
    third-party captures kept out of the repo; the replay then runs without images)."""
    if not path or not Path(path).is_file():
        return None
    from PIL import Image

    img = Image.open(path).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
from .base import ShotSource


class ReplaySource(ShotSource):
    """Plays back a JSONL file so the whole pipeline can run without the sim.

    Each line is one of:
      {"delay": 5, "gspro": {...Open Connect shot...}, "player": "Mike", "club": "DR",
       "hud": {"lie": "rough", "tiles": {"total length": "262.0"}, "to_pin": "412 yards", "score_to_par": "E"}}
      {"delay": 2, "hole": "Hole 2, par 4, 388 yards"}
      {"delay": 3, "preshot": {...Hud fields...}, "player": "Mike", "image": "data/screens/x.png"}

    `hud` takes the fields of commentator.hud.Hud, as the screen reader would have parsed them
    after the ball stopped. A shot may also carry "impact_hud" (the player box at impact) and
    "impact_image" (a screenshot at impact) for the mid-flight call.
    """

    def __init__(self, path: str, speed: float = 1.0) -> None:
        self.path = path
        self.speed = speed

    async def events(self) -> AsyncIterator[ShotEvent | HoleChangeEvent]:
        previous_hole: str | None = None
        with open(self.path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw or raw.startswith("//"):
                    continue
                item = json.loads(raw)
                delay = float(item.get("delay", 0)) / max(self.speed, 0.01)
                if delay:
                    await asyncio.sleep(delay)
                if "preshot" in item:
                    yield PreShotEvent(hud=Hud(**item["preshot"]), player_hint=item.get("player"),
                                       image=load_jpeg(item.get("image")))
                    continue
                if "hole" in item:
                    yield HoleChangeEvent(previous=previous_hole, current=item["hole"], course=item.get("course"))
                    previous_hole = item["hole"]
                    continue
                info = {"Club": item["club"]} if item.get("club") else None
                yield ShotEvent(
                    shot=Shot.from_gspro(item["gspro"], info),
                    player_hint=item.get("player"),
                    hud_hint=Hud(**item["hud"]) if "hud" in item else None,
                    impact_hud_hint=Hud(**item["impact_hud"]) if "impact_hud" in item else None,
                    impact_image=load_jpeg(item.get("impact_image")),
                )
