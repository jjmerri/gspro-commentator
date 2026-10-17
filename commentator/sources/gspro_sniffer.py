import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from ..models import HoleChangeEvent, Shot, ShotEvent
from .base import ShotSource
from .stream import JsonStreamDecoder

log = logging.getLogger(__name__)


def is_shot_message(msg: dict[str, Any]) -> bool:
    opts = msg.get("ShotDataOptions") or {}
    if opts.get("IsHeartBeat"):
        return False
    return bool(opts.get("ContainsBallData") and msg.get("BallData"))


class GSProSniffer(ShotSource):
    """Passively reads the launch-monitor <-> GSPro Open Connect traffic on loopback.

    Nothing sits between the connector and GSPro, so if this breaks, play
    carries on. Windows needs Npcap installed with "Support loopback traffic",
    and usually an elevated shell.
    """

    def __init__(self, port: int = 921, iface: str | None = None) -> None:
        self.port = port
        self.iface = iface
        self.player_info: dict[str, Any] = {}
        self._decoders: dict[tuple[int, int], JsonStreamDecoder] = {}
        self._last_shot_number: int | None = None

    async def events(self) -> AsyncIterator[ShotEvent | HoleChangeEvent]:
        async for direction, msg in self.raw_messages():
            if direction == "from_gspro":
                if msg.get("Player"):
                    self.player_info.update(msg["Player"])
                continue
            if not is_shot_message(msg):
                continue
            number = msg.get("ShotNumber")
            # Guards against TCP retransmits and connector resends.
            if number is not None and number == self._last_shot_number:
                continue
            self._last_shot_number = number
            yield ShotEvent(shot=Shot.from_gspro(msg, self.player_info))

    async def raw_messages(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        from scapy.all import TCP, AsyncSniffer, conf  # heavy import, capture extra only

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def on_packet(pkt: Any) -> None:
            if TCP not in pkt:
                return
            tcp = pkt[TCP]
            payload = bytes(tcp.payload)
            if not payload:
                return
            key = (tcp.sport, tcp.dport)
            decoder = self._decoders.setdefault(key, JsonStreamDecoder())
            direction = "to_gspro" if tcp.dport == self.port else "from_gspro"
            for msg in decoder.feed(payload):
                loop.call_soon_threadsafe(queue.put_nowait, (direction, msg))

        iface = self.iface or conf.loopback_name
        sniffer = AsyncSniffer(iface=iface, filter=f"tcp port {self.port}", prn=on_packet, store=False)
        sniffer.start()
        log.info("Sniffing GSPro Open Connect on %s port %s", iface, self.port)
        try:
            while True:
                yield await queue.get()
        finally:
            if sniffer.running:
                sniffer.stop()
