#!/usr/bin/env python3
"""Pretend to be the Pico: serves www/ and prints every command it receives.

    python3 tools/mock_pico.py            # http://localhost:8080
    python3 tools/mock_pico.py --port 9000

Open the printed address on your phone (same Wi-Fi) or a desktop browser
with mobile emulation. Standard library only, so nothing to install.
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "www")
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# The commands the real Pico understands; anything else is flagged.
KNOWN = {"move", "click", "press", "release", "scroll", "key", "media", "text", "unlock", "power", "ping"}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/ws" not in self.path:
            print("http", self.path)

    def do_GET(self):
        if self.path.split("?")[0] == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
            self.websocket()
        else:
            super().do_GET()

    def websocket(self):
        key = self.headers["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.close_connection = True
        peer = self.client_address[0]
        print(f"ws  {peer} connected")
        self.send_frame(json.dumps({"t": "hello", "name": "mock-pico", "power": True, "unlock": True}))
        moves = 0
        try:
            while True:
                text = self.read_frame()
                if text is None:
                    break
                msg = json.loads(text)
                kind = msg.get("t")
                if kind == "ping":
                    continue
                if kind == "move":
                    # Too chatty to print each one.
                    moves += 1
                    if moves % 20 == 0:
                        print(f"ws  move x{moves} (last {msg['x']:+d},{msg['y']:+d})")
                    continue
                flag = "" if kind in KNOWN else "   <-- UNKNOWN"
                print(f"ws  {text}{flag}")
        except (ConnectionError, OSError, ValueError) as e:
            print(f"ws  {peer} error: {e}")
        print(f"ws  {peer} disconnected")

    def read_exact(self, n):
        data = self.rfile.read(n)
        if len(data) < n:
            raise ConnectionError("closed")
        return data

    def read_frame(self):
        b1, b2 = self.read_exact(2)
        opcode, length = b1 & 0x0F, b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self.read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.read_exact(8))[0]
        mask = self.read_exact(4) if b2 & 0x80 else b"\0\0\0\0"
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(self.read_exact(length)))
        if opcode == 0x8:
            return None
        if opcode == 0x9:  # ping -> pong
            self.send_frame(payload, opcode=0xA)
            return self.read_frame()
        return payload.decode()

    def send_frame(self, data, opcode=0x1):
        if isinstance(data, str):
            data = data.encode()
        head = bytes([0x80 | opcode])
        n = len(data)
        head += bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n)
        self.wfile.write(head + data)
        self.wfile.flush()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), partial(Handler, directory=WWW))
    print(f"mock pico on http://localhost:{args.port}  (phone: http://{lan_ip()}:{args.port})")
    server.serve_forever()
