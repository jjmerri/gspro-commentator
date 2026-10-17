"""Replay a GSPconnect message stream through the real ConnectorLogSource, offline.

The shot feed is the booth's most failure-prone surface: it depends on how GSPconnect writes and
rotates its debug files, which only shows up with real play. This harness turns a recorded (or
synthetic) stream into a repeatable test. It writes the messages into a temp dir exactly the way
GSPconnect does, the active ConnectDebug.txt grows and, when it fills, rotates (.txt -> .txt.1 ->
.txt.2 ...) with a fresh .txt, while the real ConnectorLogSource tails it. Then it checks every
real shot was detected exactly once, and classified right (putt vs full shot).

Rotation is the point: a shot written to the active file moments before it rotates can be stranded
in .txt.1, and whether the tailer re-reads it is pure byte-offset luck. Small --rotate-bytes forces
that race often, so the harness exercises it the way a long live round would.

Usage:
  python -m tools.replay_connector --fixture tests/data/round_2026-10-06.jsonl
  python -m tools.replay_connector --synth        # adversarial synthetic stream, shots at boundaries
"""
import argparse
import asyncio
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

_STAMP = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}")


def _fs_retry(op, tries: int = 50, delay: float = 0.01):
    """Retry a filesystem op past a transient PermissionError. On Windows a file can't be renamed
    or removed while the tailer momentarily has it open (POSIX allows it), so rotation and temp-dir
    cleanup in this harness need to wait the lock out. The product code already tolerates the read
    side (it catches OSError per read)."""
    for i in range(tries):
        try:
            return op()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(delay)


def _restamp(line: str) -> str:
    """Replace the line's log timestamp with now. Recorded/synthetic stamps are in the past, and the
    source drops anything read >10s after it was logged; live play always carries a fresh stamp."""
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S,") + format(now.microsecond // 1000, "03d")
    return _STAMP.sub(stamp, line, count=1)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from commentator.sources.connector_log import ConnectorLogSource  # noqa: E402
from commentator.sources.gspro_sniffer import is_shot_message  # noqa: E402

PREFIX = " [10] INFO  VGPconnect.UneekorConForm [(null)] - "


def make_line(sn: int, when: datetime, ball: dict | None = None) -> str:
    """A real-format GSPconnect log line: a heartbeat, or a shot when `ball` is given."""
    opts = {"ContainsBallData": ball is not None, "ContainsClubData": False, "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": ball is not None, "IsHeartBeat": ball is None,
            "SendPlayerInformationToDevice": False, "DisconnectLaunchMonitor": False,
            "ShotMediaPath": "", "DoesShowIncludeLiePenalty": False}
    msg = {"DeviceID": "UNEEKOREYEXO2", "Units": "Yards", "ShotNumber": sn, "APIversion": "2",
           "ShotDataOptions": opts}
    if ball is not None:
        msg["BallData"] = ball
    stamp = when.strftime("%Y-%m-%d %H:%M:%S,") + format(when.microsecond // 1000, "03d")
    return stamp + PREFIX + json.dumps(msg)


def synth_stream() -> list[str]:
    """Heartbeats at ~1/s with shots injected, several placed to land just before a rotation so the
    stranding race fires. Includes a dead-straight VLA 0.0 putt (the real misclassification case)."""
    lines, t, sn = [], datetime(2026, 10, 6, 14, 0, 0), 500000
    # (speed, vla, carry). Real EYE XO2 putts send VLA 99999 (a sentinel the parser blanks to None);
    # one putt here reports a literal 0.0 instead, to cover both shapes.
    shots = [
        (132.7, 15.9, 225.6), (109.0, 20.4, 153.1), (15.1, 99999.0, 0.0),  # drive, approach, putt
        (124.4, 18.8, 202.4), (92.7, 20.9, 121.3), (8.0, 0.0, 0.0),        # drive, approach, flat putt
        (51.8, 30.0, 54.0), (130.4, 14.0, 250.0), (3.6, 99999.0, 0.0),     # wedge, drive, putt
    ]
    si = 0
    for i in range(400):
        # drop a shot every ~40 heartbeats, nudged to just before a rotation boundary
        if i and i % 40 == 0 and si < len(shots):
            spd, vla, carry = shots[si]
            si += 1
            ball = {"Speed": spd, "SpinAxis": 0.0, "TotalSpin": 0.0, "BackSpin": 3000, "SideSpin": 100,
                    "HLA": 0.0, "VLA": vla, "CarryDistance": carry, "TotalDistance": carry + (0 if carry == 0 else 15)}
            lines.append(make_line(sn, t, ball))
            sn += 1
            t += timedelta(milliseconds=200)
        lines.append(make_line(sn, t))
        sn += 1
        t += timedelta(seconds=1)
    return lines


def load_fixture(path: str) -> list[str]:
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda r: r["t"])
    return [r["line"] for r in rows]


def ground_truth(lines: list[str]) -> dict[int, dict]:
    """Every real shot in the stream, keyed by ShotNumber (deduping the same shot logged twice)."""
    shots: dict[int, dict] = {}
    for line in lines:
        s = line.find('{"DeviceID"')
        if s < 0:
            continue
        try:
            msg = json.loads(line[s:])
        except json.JSONDecodeError:
            continue
        if not is_shot_message(msg):
            continue
        speed = (msg.get("BallData") or {}).get("Speed") or 0
        if 0 < speed < 250:
            shots[msg["ShotNumber"]] = msg
    return shots


def expect_putt(msg: dict) -> bool:
    """What is_putt should return, derived independently from the raw message (so it's a real check,
    not the function graded against itself): a club-less slow ball whose launch is missing, a
    sentinel the parser blanks, or near zero is a putt."""
    b = msg.get("BallData") or {}
    vla_raw = b.get("VLA")
    vla = None if vla_raw is None or not -20 <= vla_raw <= 80 else vla_raw  # mirrors Shot.from_gspro
    speed = b.get("Speed") or 99
    return speed < 20 and (vla is None or vla < 5)


def _rotate(d: Path) -> None:
    """logrotate-style, as GSPconnect does it: .txt.N -> .txt.(N+1), .txt -> .txt.1, fresh .txt."""
    rolls = sorted((p for p in d.glob("ConnectDebug.txt.*") if p.suffix[1:].isdigit()),
                   key=lambda p: int(p.suffix[1:]), reverse=True)
    for p in rolls:
        _fs_retry(lambda p=p: p.rename(d / f"ConnectDebug.txt.{int(p.suffix[1:]) + 1}"))
    active = d / "ConnectDebug.txt"
    if active.exists():
        _fs_retry(lambda: active.rename(d / "ConnectDebug.txt.1"))
    (d / "ConnectDebug.txt").write_text("", encoding="utf-8")


async def replay(lines: list[str], rotate_bytes: int = 120_000, poll: float = 0.002,
                 append_every: float = 0.003, strand_shots: bool = False) -> list:
    """Replay `lines` into a temp dir with the real ConnectorLogSource tailing it.

    strand_shots forces the nastiest rotation timing: the instant a shot is written, rotate before
    the tailer can poll, so the shot lands in .txt.1 unread. That is the one way a valid shot can
    vanish without any log line, so the harness must prove the tailer re-reads it."""
    d = Path(tempfile.mkdtemp(prefix="replay_"))
    active = d / "ConnectDebug.txt"
    active.write_text("", encoding="utf-8")
    src = ConnectorLogSource(path=str(active), poll_seconds=poll)
    detected: list = []

    async def consume():
        async for ev in src.events():
            detected.append(ev)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the source prime on the empty dir before anything is written
    try:
        written = 0
        for line in lines:
            line = _restamp(line)
            is_shot = '"ContainsBallData":true' in line.replace(" ", "").lower()

            def _append(line=line):
                with open(d / "ConnectDebug.txt", "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            _fs_retry(_append)  # the tailer may momentarily hold the file open on Windows
            written += len(line) + 1
            if strand_shots and is_shot:
                _rotate(d)  # rotate immediately, no await: the shot is stranded in .txt.1 unread
                written = 0
            elif written >= rotate_bytes:
                _rotate(d)
                written = 0
            await asyncio.sleep(append_every)  # yield so the tailer polls between writes
        await asyncio.sleep(0.5)  # drain
    finally:
        task.cancel()
        try:
            await task  # let the cancelled consumer (and its in-flight read thread) settle
        except (asyncio.CancelledError, Exception):
            pass
        shutil.rmtree(d, ignore_errors=True)
    return detected


def report(lines: list[str], detected: list) -> int:
    truth = ground_truth(lines)
    got_nums = [e.shot.shot_number for e in detected]
    got_set = set(got_nums)
    missed = sorted(set(truth) - got_set)
    dups = sorted(n for n in got_set if got_nums.count(n) > 1)
    print(f"stream: {len(lines)} messages, {len(truth)} real shots")
    print(f"detected: {len(detected)} shot events, {len(got_set)} distinct")
    # classification check against the stream's own ball data
    misclass = []
    for e in detected:
        src_msg = truth.get(e.shot.shot_number)
        if not src_msg:
            continue
        if e.shot.is_putt != expect_putt(src_msg):
            misclass.append((e.shot.shot_number, e.shot.is_putt, expect_putt(src_msg)))
    ok = not missed and not dups and not misclass
    if missed:
        print(f"  MISSED {len(missed)} shots: {missed}")
        for n in missed:
            b = (truth[n].get("BallData") or {})
            print(f"    SN={n} speed={b.get('Speed')} vla={b.get('VLA')}")
    if dups:
        print(f"  DUPLICATED shots: {dups}")
    if misclass:
        print(f"  MISCLASSIFIED (SN, got_is_putt, expected): {misclass}")
    print("RESULT:", "OK - every shot detected once and classified right" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", help="JSONL of recorded messages (fields: t, line)")
    ap.add_argument("--synth", action="store_true", help="use the adversarial synthetic stream")
    ap.add_argument("--rotate-bytes", type=int, default=120_000, help="rotate the active file at this size")
    ap.add_argument("--strand", action="store_true", help="rotate the instant each shot is written (worst case)")
    args = ap.parse_args()
    if args.synth or not args.fixture:
        lines = synth_stream()
    else:
        lines = load_fixture(args.fixture)
    detected = asyncio.run(replay(lines, rotate_bytes=args.rotate_bytes, strand_shots=args.strand))
    return report(lines, detected)


if __name__ == "__main__":
    raise SystemExit(main())
