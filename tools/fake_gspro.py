"""Stand-in GSPro + launch-monitor connector talking Open Connect on localhost.

Lets the sniffer be tested on any machine:
    python tools/fake_gspro.py            # terminal 1
    python -m commentator sniff           # terminal 2 (or `run` with source.type: gspro_sniffer)
On macOS use --port 9210 for both; only root can bind loopback ports below 1024.
"""

import argparse
import json
import socket
import threading
import time

SHOTS = [
    ("DR", {"Speed": 165.3, "SpinAxis": -3.5, "TotalSpin": 2450, "HLA": -1.2, "VLA": 12.4, "CarryDistance": 281.7}),
    ("7I", {"Speed": 121.8, "SpinAxis": 22.0, "TotalSpin": 6400, "HLA": 9.1, "VLA": 17.9, "CarryDistance": 158.3}),
    ("PT", {"Speed": 7.5, "SpinAxis": 0, "TotalSpin": 0, "HLA": 0.4, "VLA": 1.0, "CarryDistance": 0}),
]


def gspro(srv: socket.socket) -> None:
    conn, _ = srv.accept()
    clubs = iter(c for c, _ in SHOTS)
    # GSPro announces the player's club before each shot.
    conn.sendall(json.dumps({"Code": 201, "Message": "GSPro Player Information",
                             "Player": {"Handed": "RH", "Club": next(clubs)}}).encode())
    buf = b""
    while data := conn.recv(4096):
        buf += data
        if b"\"BallData\"" in data:
            conn.sendall(json.dumps({"Code": 200, "Message": "Shot received successfully", "Player": None}).encode())
            club = next(clubs, None)
            if club:
                conn.sendall(json.dumps({"Code": 201, "Message": "GSPro Player Information",
                                         "Player": {"Handed": "RH", "Club": club}}).encode())


def connector(port: int, gap: float) -> None:
    s = socket.create_connection(("127.0.0.1", port))
    for n, (_, ball) in enumerate(SHOTS, start=1):
        hb = {"DeviceID": "FakeLM", "Units": "Yards", "APIversion": "1",
              "ShotDataOptions": {"ContainsBallData": False, "ContainsClubData": False,
                                  "LaunchMonitorIsReady": True, "IsHeartBeat": True}}
        s.sendall(json.dumps(hb).encode())
        time.sleep(gap)
        shot = {"DeviceID": "FakeLM", "Units": "Yards", "ShotNumber": n, "APIversion": "1", "BallData": ball,
                "ShotDataOptions": {"ContainsBallData": True, "ContainsClubData": False,
                                    "LaunchMonitorIsReady": True, "IsHeartBeat": False}}
        # Split the message across two writes to exercise stream reassembly.
        raw = json.dumps(shot).encode()
        s.sendall(raw[:40])
        time.sleep(0.05)
        s.sendall(raw[40:])
        print(f"sent shot {n}", flush=True)
    time.sleep(1)
    s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=921)
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between shots")
    ap.add_argument("--start-delay", type=float, default=3.0, help="time to get the sniffer running")
    args = ap.parse_args()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", args.port))
    except PermissionError:
        raise SystemExit(f"Can't bind port {args.port}; on macOS use --port 9210")
    srv.listen(1)
    threading.Thread(target=gspro, args=(srv,), daemon=True).start()
    time.sleep(args.start_delay)
    connector(args.port, args.gap)
