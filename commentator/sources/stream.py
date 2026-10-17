import json
from typing import Any

# Real messages are a few KB at most, so anything bigger that still won't parse is a
# corrupt fragment (e.g. sniffing started mid-message).
MAX_BUFFER = 16 * 1024


class JsonStreamDecoder:
    """Splits a TCP byte stream into JSON objects.

    GSPro Open Connect sends bare JSON objects with no framing, and a single
    TCP segment can hold part of a message or several messages back to back.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._decoder = json.JSONDecoder()

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        self._buf += data.decode("utf-8", errors="ignore")
        out: list[dict[str, Any]] = []
        while True:
            start = self._buf.find("{")
            if start < 0:
                self._buf = ""
                return out
            self._buf = self._buf[start:]
            try:
                obj, end = self._decoder.raw_decode(self._buf)
            except json.JSONDecodeError:
                # Usually a message split across segments. If the buffer keeps
                # growing it's garbage instead, so skip past this brace and resync.
                if len(self._buf) > MAX_BUFFER:
                    self._buf = self._buf[1:]
                    continue
                return out
            self._buf = self._buf[end:]
            if isinstance(obj, dict):
                out.append(obj)
