# Couch Controller Web

A phone remote for the Beelink that guests can use from a browser, in the same
CRT style as the Retroid app. It talks to the same Pico 2 W: the Pico serves
the page, the phone sends commands back over a WebSocket, and the Pico turns
them into USB keyboard, mouse and media keys.

```
phone browser ──http://couchcommander.local──▶ Pico 2 W ──USB HID──▶ Beelink
              ◀──────── ws://…/ws (JSON) ─────▶
```

## What's here

| Path | What it is |
|---|---|
| `www/index.html` | The whole web app: one file, no build step, no internet needed |
| `pico/couch_web.py` | CircuitPython module: serves the page, handles the WebSocket |
| `pico/code_example.py` | How to wire it into the existing `code.py` (3 lines) |
| `pico/settings.toml.example` | Unlock secret and the power-menu switch |
| `tools/mock_pico.py` | Fake Pico for testing the page on a laptop |

## Try it without the Pico

```bash
python3 tools/mock_pico.py
```

Open the address it prints on your phone (same Wi-Fi). Every button press is
printed in the terminal. Nothing to install, just Python 3.

## Putting it on the Pico

1. Copy `www/index.html` to `CIRCUITPY/www/index.html`.
2. Copy `pico/couch_web.py` to `CIRCUITPY/`.
3. Make sure `CIRCUITPY/lib` has `adafruit_httpserver` (4.x) and `adafruit_hid`
   (from the CircuitPython bundle, or `circup install adafruit_httpserver`).
4. Add the three marked lines from `pico/code_example.py` to `code.py`, reusing
   the `Keyboard` / `Mouse` / `ConsumerControl` objects it already has. Both
   servers run in the same loop, so the Retroid's must not block (use a 0 or
   short timeout on its sockets).
5. Add the settings from `pico/settings.toml.example` to `settings.toml`.
6. Guests open **http://couchcommander.local** (or the Pico's IP; some
   Android phones don't resolve `.local`). A QR code on the fridge helps.

The page has to be loaded over `http://`. Browsers block an `https://` page
(e.g. GitHub Pages) from opening a plain `ws://` connection, and the Pico
can't do https. That's the main reason the Pico serves the page itself.

## Controls

Same layout as the Retroid app, without FUN STUFF and GAMEPAD. The freed slot
holds QUICKPAD, so both orientations have QUICKPAD / KEYBOARD / BACK/ESC down
the right-hand column.

- **Touchpad**: drag = move, tap = click, two-finger tap = right click,
  two-finger drag = scroll, tap then hold-and-drag = click-and-drag.
- **Scroll strip**: drag up and down.
- **D-pad, PLAY/PAUSE, BACK/ESC, VOLUME**: the same keys the Retroid sends
  (arrows, Play/Pause media key, Escape, volume media keys). Hold arrows or
  volume to repeat.
- **ACTIONS**: launcher home (`Ctrl+Alt+Shift+H`), switch apps
  (`Ctrl+Alt+Shift+S`), fullscreen, mute, tracks, YouTube keys, zoom and so on.
- **QUICKPAD**: keys phones lack: Tab, Page Up/Down, F5, F11, Win…
- **KEYBOARD**: types with the phone's own keyboard. LIVE sends each character
  as you type; turn it off to write a line and send it in one go.
- **UNLOCK**: asks the Pico to type the Windows PIN/password. The secret stays
  on the Pico, so guests never see it. Disabled if no secret is set.
- **POWER**: sleep / lock / restart / shut down, hold to confirm. Can be
  switched off on the Pico (`COUCH_WEB_POWER = "0"`).
- **[ X ]**: closes the window on screen (Alt+F4), after a confirm.
- **SETUP**: Pico address, pointer speed and acceleration, scroll speed,
  vibrate on press, and the same colour themes as the Retroid app. Saved per phone.
- **LEGEND**: a plain-English guide for guests.

The ACTIONS, QUICKPAD and keyboard-key lists are in the `CONFIG` block at the
top of the script in `index.html`, ready to edit.

## Protocol

JSON text messages over `ws://<pico>/ws`. Key names are `adafruit_hid`
`Keycode` names, media names are `ConsumerControlCode` names.

Phone → Pico:

| Message | Does |
|---|---|
| `{"t":"move","x":5,"y":-3}` | Move the pointer (relative px) |
| `{"t":"click","b":"left"}` | Click `left` / `right` / `middle` |
| `{"t":"press","b":"left"}` / `{"t":"release","b":"left"}` | Hold / let go (drag); `release` with no `b` lets go of all |
| `{"t":"scroll","v":1}` | Wheel notches, positive = up |
| `{"t":"key","k":["CONTROL","ALT","SHIFT","H"]}` | Press keys together, then release |
| `{"t":"media","k":"VOLUME_INCREMENT"}` | Media key |
| `{"t":"text","s":"hello"}` | Type text (US layout) |
| `{"t":"unlock"}` | Type the unlock secret from `settings.toml` |
| `{"t":"power","a":"sleep"}` | `sleep` / `lock` / `restart` / `shutdown` |
| `{"t":"ping"}` | Keep-alive, every 5 s |

Pico → phone: `{"t":"hello","power":true,"unlock":true}` on connect (greys
out buttons that are switched off), and `{"t":"err","msg":"…"}`.

If the Pico disconnects, the Pico releases every key and mouse button, so a
phone that drops mid-drag can't leave something held.

## Not tested yet

The web page and protocol are tested against `tools/mock_pico.py`. The
CircuitPython side is written against the `adafruit_httpserver` 4.x and
`adafruit_hid` APIs, but hasn't run on the real Pico yet. Things to check at
home:

- It fits alongside the existing Retroid server in `code.py`.
- The UNLOCK timings (wake, Space, wait, type) match how the Retroid's UNLOCK
  behaves. If the Retroid already has a working sequence, copy that into
  `_unlock`.
- The Win+X → U → S/R/U power sequence works on this Windows build.
