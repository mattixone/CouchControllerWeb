# Couch Controller Web

A phone remote for the Beelink that guests can use from a browser, in the same
CRT style as the Retroid app. Couch Launcher on the Beelink serves the page,
and the phone sends its button presses over a WebSocket to whichever of these
answers:

- **The Pico 2 W** (once it runs `pico/couch_web.py`): turns them into USB
  keyboard, mouse and media keys. Works everywhere, including UNLOCK at the
  Windows lock screen.
- **Couch Launcher itself**: presses the keys from Windows. Works with no Pico
  changes; everything except UNLOCK, which Windows blocks for apps.

```
phone ──http://<beelink-ip>────────▶ Couch Launcher (page; keys if no Pico)
      ──ws://<pico>/ws (JSON)──────▶ Pico 2 W ──USB HID──▶ Beelink
```

The status line shows `LINKED PICO` or `LINKED PC`. The launcher checks for the
Pico in the background and tells the page to try it first once it answers.
None of this touches the Retroid's link to the Pico.

The Pico can serve the page itself too, at `http://couchcommander.local`.
That's the fallback for when the Beelink is asleep (the launcher can't serve
anything then, but the Pico can, and a keypress wakes the PC).

## What's here

| Path | What it is |
|---|---|
| `www/index.html` | The whole web app: one file, no build step, no internet needed. Couch Launcher ships a copy of it |
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

## Setting it up

**Beelink:** nothing to do beyond updating Couch Launcher. It serves the page
from the next release; Settings › PHONE REMOTE shows the QR code and address
for guests. Allow it through Windows Firewall when asked (see the
[launcher README](https://github.com/mattixone/couch-launcher#phone-remote)).

**Pico:**

1. Copy `pico/couch_web.py` to `CIRCUITPY/`.
2. Optional, for the asleep-Beelink fallback: copy `www/index.html` to
   `CIRCUITPY/www/index.html`. (Without it, only the launcher serves the page.)
3. Make sure `CIRCUITPY/lib` has `adafruit_httpserver` (4.x) and `adafruit_hid`
   (from the CircuitPython bundle, or `circup install adafruit_httpserver`).
4. Add the three marked lines from `pico/code_example.py` to `code.py`, reusing
   the `Keyboard` / `Mouse` / `ConsumerControl` objects it already has. Both
   servers run in the same loop, so the Retroid's must not block (use a 0 or
   short timeout on its sockets).
5. Add the settings from `pico/settings.toml.example` to `settings.toml`.

The page has to be loaded over `http://`. Browsers block an `https://` page
(e.g. GitHub Pages) from opening a plain `ws://` connection, and the Pico
can't do https, which is why the page comes from a machine on the home network.

**How the page finds the Pico**, first that applies:
1. An address typed into SETUP (or `?host=` in the URL).
2. Served by Couch Launcher: the addresses it writes into the page's
   `couch-pico` tag, in the order to try them: the Pico (IP, then
   `couchcommander.local`) and `@self`, the launcher. Pico first only once the
   launcher has seen it answer. If one doesn't connect within a few seconds,
   the page tries the next.
3. Served by the Pico: the Pico itself.

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
- Couch Launcher's web server is tested (run on Linux, serving the page to a
  browser that then drove the mock Pico), but the launcher hasn't been built
  with the .NET SDK or run on Windows with it yet.
