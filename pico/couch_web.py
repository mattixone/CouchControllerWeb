# couch_web.py: the phone remote (CouchControllerWeb), Pico side.
#
# A small WebSocket server on TCP port 80 that takes the phone page's button
# presses and turns them into USB HID input, alongside the Retroid's UDP link.
# Couch Launcher serves the page itself; this only takes the presses, which
# beats the launcher pressing keys from Windows because a real USB keyboard
# also works on the lock screen (UNLOCK).
#
# No libraries beyond adafruit_hid, and nothing here ever blocks: code.py
# calls poll() from its receive loop and it returns straight away when there's
# nothing to do, so the Retroid's input is never held up.
#
#     web = couch_web.CouchWeb(pool, kbd, layout, mouse, consumer,
#                              move_mouse=move_mouse, do_power=do_power)
#     ...in the loop:  web.poll()

import json
import time

try:
    import errno
    _AGAIN = (getattr(errno, "EAGAIN", 11), getattr(errno, "ETIMEDOUT", 116))
except ImportError:
    _AGAIN = (11, 116)

try:
    from binascii import b2a_base64
except ImportError:  # pragma: no cover
    from ubinascii import b2a_base64

from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse

MAX_CLIENTS = 3          # phones at once; sockets are scarce on the Pico
MAX_MOVE = 400           # px per message, so a glitch can't fling the pointer
MAX_TEXT = 300           # characters per text message
POLL_EVERY_NS = 4_000_000  # look for web traffic at most every 4 ms
HEAD_TIMEOUT_NS = 3_000_000_000

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_BUTTONS = {"left": Mouse.LEFT_BUTTON, "right": Mouse.RIGHT_BUTTON, "middle": Mouse.MIDDLE_BUTTON}


def _sha1(data):
    """SHA-1 for the WebSocket handshake. hashlib where the firmware has it,
    otherwise a plain version (it only ever hashes ~60 bytes per connection)."""
    try:
        import hashlib
        return hashlib.sha1(data).digest()
    except (ImportError, AttributeError, ValueError):
        pass
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    msg = bytearray(data)
    bits = len(msg) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += bits.to_bytes(8, "big")
    mask = 0xFFFFFFFF
    for chunk in range(0, len(msg), 64):
        w = [int.from_bytes(msg[chunk + i:chunk + i + 4], "big") for i in range(0, 64, 4)]
        for i in range(16, 80):
            x = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]
            w.append(((x << 1) | (x >> 31)) & mask)
        a, b, c, d, e = h
        for i in range(80):
            if i < 20:
                f, k = (b & c) | (~b & d), 0x5A827999
            elif i < 40:
                f, k = b ^ c ^ d, 0x6ED9EBA1
            elif i < 60:
                f, k = (b & c) | (b & d) | (c & d), 0x8F1BBCDC
            else:
                f, k = b ^ c ^ d, 0xCA62C1D6
            t = ((((a << 5) | (a >> 27)) & mask) + (f & mask) + e + k + w[i]) & mask
            a, b, c, d, e = t, a, ((b << 30) | (b >> 2)) & mask, c, d
        h = [(x + y) & mask for x, y in zip(h, (a, b, c, d, e))]
    return b"".join(x.to_bytes(4, "big") for x in h)


def _origin_ok(origin):
    """Only pages served on the home network may connect (Couch Launcher's,
    on the Beelink), so a website a guest has open can't drive the PC."""
    if origin is None:
        return True  # not a browser
    host = origin.split("://", 1)[-1].split("/", 1)[0]
    if host.startswith("["):
        return host.startswith("[fe80") or host.startswith("[::1")
    host = host.split(":", 1)[0].lower()
    if host == "localhost" or host.endswith(".local"):
        return True
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return False
    a, b = int(parts[0]), int(parts[1])
    return a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


def _lookup(table, name):
    # Plain constant names only, so a message can't reach anything else on the class.
    if not isinstance(name, str) or not name or not all(c.isupper() or c.isdigit() or c == "_" for c in name):
        return None
    value = getattr(table, name, None)
    return value if isinstance(value, int) else None


def _no_data(exc):
    return exc.args and exc.args[0] in _AGAIN


class _Client:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""
        self.open = False  # handshake done
        self.since = time.monotonic_ns()


class CouchWeb:
    def __init__(self, pool, kbd, layout, mouse, consumer, move_mouse=None, do_power=None,
                 unlock_secret="", allow_power=True, port=80):
        self.kbd = kbd
        self.layout = layout
        self.mouse = mouse
        self.consumer = consumer
        self.move_mouse = move_mouse
        self.do_power = do_power
        self.unlock_secret = unlock_secret or ""
        self.allow_power = allow_power
        self.clients = []
        self.held = 0           # mouse buttons a phone is holding (never the Retroid's)
        self.next_poll = 0
        self.rx = bytearray(1024)
        self.server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        try:
            self.server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
        except Exception:
            pass
        self.server.bind(("0.0.0.0", port))
        self.server.listen(2)
        self.server.setblocking(False)
        print("Phone remote listening on TCP", port)

    # ------------------------------------------------------------ plumbing

    def poll(self):
        """Call as often as you like; does real work at most every few ms."""
        now = time.monotonic_ns()
        if now < self.next_poll:
            return
        self.next_poll = now + POLL_EVERY_NS
        self._accept()
        for client in list(self.clients):
            try:
                self._read(client, now)
            except OSError:
                self._drop(client)

    def _accept(self):
        try:
            sock, _ = self.server.accept()
        except OSError:
            return  # nobody waiting
        sock.setblocking(False)
        client = _Client(sock)
        self.clients.append(client)
        if len(self.clients) > MAX_CLIENTS:
            self._drop(self.clients[0])

    def _read(self, client, now):
        try:
            n = client.sock.recv_into(self.rx)
        except OSError as exc:
            if not _no_data(exc):
                raise
            if not client.open and now - client.since > HEAD_TIMEOUT_NS:
                self._drop(client)
            return
        if n == 0:
            self._drop(client)  # phone hung up
            return
        client.buf += bytes(self.rx[:n])
        if len(client.buf) > 4096:
            self._drop(client)
            return
        if not client.open:
            self._handshake(client)
        if client.open:
            self._frames(client)

    def _send(self, client, data):
        view = memoryview(data)
        tries = 0
        while len(view):
            try:
                sent = client.sock.send(view)
            except OSError as exc:
                if _no_data(exc) and tries < 50:
                    tries += 1
                    time.sleep(0.001)
                    continue
                raise
            view = view[sent:]

    def _drop(self, client):
        if client in self.clients:
            self.clients.remove(client)
        try:
            client.sock.close()
        except Exception:
            pass
        # Let go of anything this phone was holding: its own buttons only,
        # never keys the Retroid is holding down.
        if self.held:
            self.mouse.release(self.held)
            self.held = 0

    # ----------------------------------------------------------- websocket

    def _handshake(self, client):
        end = client.buf.find(b"\r\n\r\n")
        if end < 0:
            return
        head = client.buf[:end].decode("utf-8", "replace")
        client.buf = client.buf[end + 4:]
        lines = head.split("\r\n")
        parts = lines[0].split(" ")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        path = parts[1].split("?", 1)[0] if len(parts) > 1 else ""
        key = headers.get("sec-websocket-key")
        if path != "/ws" or headers.get("upgrade", "").lower() != "websocket" or not key:
            body = b"Couch Commander phone remote: open it from Couch Launcher.\n"
            self._send(client, b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: "
                       + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            self._drop(client)
            return
        if not _origin_ok(headers.get("origin")):
            print("Phone remote: refused", headers.get("origin"))
            self._send(client, b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            self._drop(client)
            return
        accept = b2a_base64(_sha1(key.encode() + _GUID)).strip()
        self._send(client, b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                   b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
        client.open = True
        self._reply(client, {"t": "hello", "name": "couchcommander",
                             "power": bool(self.allow_power and self.do_power),
                             "unlock": bool(self.unlock_secret)})

    def _frames(self, client):
        buf = client.buf
        while len(buf) >= 2:
            opcode = buf[0] & 0x0F
            masked = buf[1] & 0x80
            length = buf[1] & 0x7F
            at = 2
            if length == 126:
                if len(buf) < 4:
                    break
                length = int.from_bytes(buf[2:4], "big")
                at = 4
            elif length == 127:
                self._drop(client)  # nothing we expect is that big
                return
            if len(buf) < at + (4 if masked else 0) + length:
                break
            mask = buf[at:at + 4] if masked else b"\0\0\0\0"
            at += 4 if masked else 0
            payload = bytes(b ^ mask[i & 3] for i, b in enumerate(buf[at:at + length]))
            buf = buf[at + length:]
            if opcode == 0x1:
                self._handle(client, payload)
            elif opcode == 0x8:
                try:
                    self._send(client, b"\x88\x00")
                except OSError:
                    pass
                self._drop(client)
                return
            elif opcode == 0x9:
                self._frame(client, payload, 0xA)  # ping -> pong
            if client not in self.clients:
                return
        client.buf = buf

    def _frame(self, client, payload, opcode=0x1):
        n = len(payload)
        head = bytes((0x80 | opcode, n)) if n < 126 else bytes((0x80 | opcode, 126)) + n.to_bytes(2, "big")
        self._send(client, head + payload)

    def _reply(self, client, msg):
        try:
            self._frame(client, json.dumps(msg).encode())
        except OSError:
            self._drop(client)

    # ------------------------------------------------------------- commands

    def _handle(self, client, payload):
        try:
            msg = json.loads(payload)
            kind = msg.get("t")
        except (ValueError, AttributeError):
            return
        try:
            if kind == "move":
                x = max(-MAX_MOVE, min(MAX_MOVE, int(msg.get("x", 0))))
                y = max(-MAX_MOVE, min(MAX_MOVE, int(msg.get("y", 0))))
                if self.move_mouse:
                    self.move_mouse(x, y)
                else:
                    self.mouse.move(x=x, y=y)
            elif kind == "scroll":
                self.mouse.move(wheel=max(-20, min(20, int(msg.get("v", 0)))))
            elif kind == "click":
                self.mouse.click(_BUTTONS.get(msg.get("b"), Mouse.LEFT_BUTTON))
            elif kind == "press":
                button = _BUTTONS.get(msg.get("b"), Mouse.LEFT_BUTTON)
                self.held |= button
                self.mouse.press(button)
            elif kind == "release":
                button = _BUTTONS.get(msg.get("b")) or self.held
                if button:
                    self.mouse.release(button)
                    self.held &= ~button
            elif kind == "key":
                codes = [_lookup(Keycode, n) for n in (msg.get("k") or [])[:6]]
                if not codes or None in codes:
                    return self._reply(client, {"t": "err", "msg": "unknown key"})
                self.kbd.press(*codes)
                # Only these keys: the Retroid may be holding others down.
                self.kbd.release(*codes)
            elif kind == "media":
                code = _lookup(ConsumerControlCode, msg.get("k"))
                if code is None:
                    return self._reply(client, {"t": "err", "msg": "unknown media key"})
                self.consumer.send(code)
            elif kind == "text":
                self._type(str(msg.get("s", ""))[:MAX_TEXT])
            elif kind == "unlock":
                self._unlock(client)
            elif kind == "power":
                self._power(client, msg.get("a"))
            # "ping" and anything newer than this firmware: nothing to do
        except Exception as exc:  # one bad message must never stop the Pico
            print("Phone remote:", kind, exc)

    def _type(self, text):
        try:
            self.layout.write(text)
        except ValueError:
            # Something the US layout can't type (emoji, accents): skip just that.
            for ch in text:
                try:
                    self.layout.write(ch)
                except ValueError:
                    pass

    def _unlock(self, client):
        # The PIN lives here on the Pico; phones only ever ask for "unlock".
        # Takes about two seconds, during which the Retroid waits too.
        if not self.unlock_secret:
            return self._reply(client, {"t": "err", "msg": "unlock not set up on the pico"})
        self.mouse.move(x=1)          # wake the screen
        self.mouse.move(x=-1)
        time.sleep(0.6)
        self.kbd.send(Keycode.SPACE)  # lift the lock-screen curtain
        time.sleep(1.2)
        self.layout.write(self.unlock_secret)
        # A Windows Hello PIN signs in by itself; a password needs Enter.
        if not self.unlock_secret.isdigit():
            self.kbd.send(Keycode.ENTER)

    def _power(self, client, action):
        if not (self.allow_power and self.do_power):
            return self._reply(client, {"t": "err", "msg": "power is switched off"})
        if action == "lock":
            self.kbd.send(Keycode.GUI, Keycode.L)
        elif action in ("sleep", "restart", "shutdown"):
            self.do_power(action)
