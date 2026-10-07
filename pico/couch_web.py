# Couch Commander web remote, Pico side.
#
# Serves www/index.html to guests' phones and turns their WebSocket messages
# into USB keyboard/mouse/media input on the Beelink. Built to sit alongside
# the existing Retroid server: create it once, call poll() from the main loop.
#
#     web = CouchWeb(pool, mouse, keyboard, layout, consumer)
#     web.start()
#     while True:
#         web.poll()
#         ...existing Retroid handling...
#
# Needs adafruit_httpserver (4.x) and adafruit_hid in /lib, and the web page
# copied to /www/index.html on CIRCUITPY. Settings (all optional) come from
# settings.toml, see settings.toml.example.

import json
import os
import time

import wifi
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse
from adafruit_httpserver import GET, FileResponse, Server, Websocket

MAX_CLIENTS = 4      # guests connected at once; the oldest is dropped past this
MAX_MOVE = 400       # px per message, so a glitch can't fling the pointer
MAX_TEXT = 300       # characters per text message

BUTTONS = {"left": Mouse.LEFT_BUTTON, "right": Mouse.RIGHT_BUTTON, "middle": Mouse.MIDDLE_BUTTON}


def _flag(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _lookup(table, name):
    # Only plain constant names, so a message can't reach anything else
    # on the class.
    if not isinstance(name, str) or not name or not all(c.isupper() or c.isdigit() or c == "_" for c in name):
        return None
    value = getattr(table, name, None)
    return value if isinstance(value, int) else None


class CouchWeb:
    def __init__(self, pool, mouse, keyboard, layout, consumer, root="/www", port=80):
        self.mouse = mouse
        self.keyboard = keyboard
        self.layout = layout
        self.consumer = consumer
        self.port = port
        self.clients = []
        self.allow_power = _flag("COUCH_WEB_POWER", True)
        self.unlock_secret = os.getenv("COUCH_UNLOCK_SECRET") or ""

        self.server = Server(pool, root, debug=False)

        @self.server.route("/", GET)
        def index(request):
            return FileResponse(request, "index.html", root)

        @self.server.route("/ws", GET)
        def socket(request):
            ws = Websocket(request)
            self.clients.append(ws)
            if len(self.clients) > MAX_CLIENTS:
                self._drop(self.clients[0])
            hello = {"t": "hello", "name": "couchcommander", "power": self.allow_power, "unlock": bool(self.unlock_secret)}
            try:
                ws.send_message(json.dumps(hello), fail_silently=True)
            except Exception:
                pass
            return ws

    def start(self):
        self.server.start(str(wifi.radio.ipv4_address), self.port)
        print("couch web on http://%s:%d" % (wifi.radio.ipv4_address, self.port))

    def poll(self):
        try:
            self.server.poll()
        except Exception as e:  # a bad request shouldn't take the Retroid link down with it
            print("couch web:", e)
        for ws in list(self.clients):
            try:
                data = ws.receive(fail_silently=True)
            except Exception:
                data = None
                self._drop(ws)
                continue
            if getattr(ws, "closed", False):
                self._drop(ws)
                continue
            if data:
                self._handle(ws, data)

    def _drop(self, ws):
        if ws in self.clients:
            self.clients.remove(ws)
        try:
            ws.close()
        except Exception:
            pass
        # Never leave a button or key held if a phone vanishes mid-drag.
        self.mouse.release_all()
        self.keyboard.release_all()

    def _reply(self, ws, msg):
        try:
            ws.send_message(json.dumps(msg), fail_silently=True)
        except Exception:
            pass

    def _handle(self, ws, data):
        try:
            msg = json.loads(data)
            kind = msg.get("t")
        except Exception:
            return
        try:
            if kind == "move":
                x = max(-MAX_MOVE, min(MAX_MOVE, int(msg.get("x", 0))))
                y = max(-MAX_MOVE, min(MAX_MOVE, int(msg.get("y", 0))))
                self.mouse.move(x=x, y=y)
            elif kind == "scroll":
                self.mouse.move(wheel=max(-20, min(20, int(msg.get("v", 0)))))
            elif kind == "click":
                self.mouse.click(BUTTONS.get(msg.get("b"), Mouse.LEFT_BUTTON))
            elif kind == "press":
                self.mouse.press(BUTTONS.get(msg.get("b"), Mouse.LEFT_BUTTON))
            elif kind == "release":
                button = BUTTONS.get(msg.get("b"))
                self.mouse.release(button) if button else self.mouse.release_all()
            elif kind == "key":
                names = msg.get("k") or []
                codes = [_lookup(Keycode, n) for n in names[:6]]
                if not codes or None in codes:
                    return self._reply(ws, {"t": "err", "msg": "unknown key"})
                self.keyboard.press(*codes)
                self.keyboard.release_all()
            elif kind == "media":
                code = _lookup(ConsumerControlCode, msg.get("k"))
                if code is None:
                    return self._reply(ws, {"t": "err", "msg": "unknown media key"})
                self.consumer.send(code)
            elif kind == "text":
                self._type(str(msg.get("s", ""))[:MAX_TEXT])
            elif kind == "unlock":
                self._unlock(ws)
            elif kind == "power":
                self._power(ws, msg.get("a"))
            elif kind == "ping":
                pass
        except Exception as e:
            print("couch web:", kind, e)
            self.keyboard.release_all()

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

    def _tap(self, *codes):
        self.keyboard.press(*codes)
        self.keyboard.release_all()

    # The secret lives here on the Pico; phones only ever ask for "unlock".
    # Tune the waits to match how the Retroid app's UNLOCK behaves.
    def _unlock(self, ws):
        if not self.unlock_secret:
            return self._reply(ws, {"t": "err", "msg": "unlock not set up"})
        self.mouse.move(x=1)          # wake the screen
        self.mouse.move(x=-1)
        time.sleep(0.6)
        self._tap(Keycode.SPACE)      # lift the lock-screen curtain
        time.sleep(1.2)
        self.layout.write(self.unlock_secret)
        # A Windows Hello PIN signs in by itself; a password needs Enter.
        if _flag("COUCH_UNLOCK_ENTER", not self.unlock_secret.isdigit()):
            self._tap(Keycode.ENTER)

    # Win+X menu: U opens "Shut down or sign out", then S/R/U.
    def _power(self, ws, action):
        if not self.allow_power:
            return self._reply(ws, {"t": "err", "msg": "power is switched off"})
        if action == "lock":
            return self._tap(Keycode.GUI, Keycode.L)
        letter = {"sleep": Keycode.S, "restart": Keycode.R, "shutdown": Keycode.U}.get(action)
        if letter is None:
            return
        self._tap(Keycode.GUI, Keycode.X)
        time.sleep(0.7)
        self._tap(Keycode.U)
        time.sleep(0.5)
        self._tap(letter)
