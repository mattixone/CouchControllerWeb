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

**The Pico serves the page too**, at `http://<pico-ip>` or
`http://couchcommander.local`. That's the one to use when the Beelink is
asleep, restarting or at the sign-in screen: Couch Launcher isn't running then,
but the Pico always is, so you can open the page and press a button (a
keypress wakes the PC; UNLOCK gets past the lock screen).

## What's here

| Path | What it is |
|---|---|
| `www/index.html` | The whole web app: one file, no build step, no internet needed. Couch Launcher ships a copy of it |
| `pico/couch_web.py` | The Pico side: a small non-blocking WebSocket server, no libraries beyond `adafruit_hid` |
| `pico/code_example.py` | The three additions that fit it into `code.py` |
| `pico/www/index.html.gz` | The page, pre-compressed for the Pico to serve (rebuilt by `tools/build_pico_page.py`) |
| `tools/build_pico_page.py` | Regenerates `pico/www/index.html.gz` from `www/index.html` |
| `pico/config_additions.py` | Optional settings for `config.py`: unlock PIN, power menu, on/off |
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

**Pico:** (optional; without it the launcher presses the keys, all but UNLOCK)

1. Copy `pico/couch_web.py` to `CIRCUITPY/`, and `pico/www/index.html.gz` to
   `CIRCUITPY/www/index.html.gz` (make the `www` folder). That's the page the
   Pico serves. After changing `www/index.html`, run
   `python3 tools/build_pico_page.py` and copy the new `.gz` over.
2. Use the `code.py` with the phone remote added (it's the firmware's own
   `code.py` plus the three additions in `pico/code_example.py`). If
   `couch_web.py` is missing or fails, the Retroid link carries on as before.
3. Optional: add the lines from `pico/config_additions.py` to `config.py`,
   at least `UNLOCK_PIN` for UNLOCK to work.

Nothing to add to `lib`: it only needs `adafruit_hid`, which is already there.
The phone remote listens on TCP port 80, separate from the Retroid's UDP port,
and is polled from the same loop at most every 4 ms without ever blocking. The
page goes out 1 KB per poll, so loading it never holds up the Retroid. Give the
Pico a fixed address in your router (a DHCP reservation) so the address you
bookmark never changes.
Only pages served on the home network may connect (private IPs and `.local`
names), so a website a guest has open can't reach it.

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
3. Served by the Pico (or the mock Pico): whoever served the page.

## Controls

Touchpad on top (on the right in landscape), and under it a 4×4 keypad built
around a d-pad with a lit-up ENTER in the middle:

```
SCROLL   UNLOCK  VOL +   ACTIONS
SCROLL     ▲     VOL −   ACTIONS
  ◄      ENTER     ►     KEYBOARD
PLAY/PAUSE ▼   BACK/ESC  KEYBOARD
```

- **Touchpad**: drag = move, tap = click, two-finger tap = right click,
  two-finger drag = scroll, tap then hold-and-drag = click-and-drag.
- **Scroll strip**: drag up and down.
- **D-pad, PLAY/PAUSE, BACK/ESC, VOLUME**: the same keys the Retroid sends
  (arrows, Play/Pause media key, Escape, volume media keys). Hold arrows or
  volume to repeat.
- **ENTER**: selects, like OK on a TV remote.
- **ACTIONS**: launcher home (`Ctrl+Alt+Shift+H`), switch apps
  (`Ctrl+Alt+Shift+S`), fullscreen, mute, tracks, YouTube keys, zoom and so on.
- **KEYBOARD**: types with the phone's own keyboard. LIVE sends each character
  as you type; turn it off to write a line and send it in one go.
- **UNLOCK**: asks the Pico to type the Windows PIN/password. The secret stays
  on the Pico (`UNLOCK_PIN` in `config.py`), so guests never see it. Greyed
  out when there's no PIN, or when the page is linked to the PC instead.
- **POWER**: sleep / lock / restart / shut down, hold to confirm. Can be
  switched off on the Pico (`WEB_POWER = False`) and in Couch Launcher
  (`PhoneRemotePower`).
- **[ X ]**: closes the window on screen (Alt+F4), after a confirm.
- **SETUP**: Pico address, pointer speed and acceleration, scroll speed,
  vibrate on press, and the same colour themes as the Retroid app. Saved per phone.
- **LEGEND**: a plain-English guide for guests.

The ACTIONS and keyboard-key lists are in the `CONFIG` block at the
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
| `{"t":"unlock"}` | Type `UNLOCK_PIN` from the Pico's `config.py` |
| `{"t":"power","a":"sleep"}` | `sleep` / `lock` / `restart` / `shutdown` |
| `{"t":"ping"}` | Keep-alive, every 5 s |

Pico → phone: `{"t":"hello","power":true,"unlock":true}` on connect (greys
out buttons that are switched off), and `{"t":"err","msg":"…"}`.

If the Pico disconnects, the Pico releases every key and mouse button, so a
phone that drops mid-drag can't leave something held.

## Testing

- **Page**: driven in a mobile browser against `tools/mock_pico.py`.
- **Couch Launcher's side**: its server ran on Linux with the Windows key
  presses stubbed out, serving the page to a browser that drove it.
- **Pico side**: the real `code.py` and `couch_web.py` ran under desktop Python
  with the real `adafruit_hid` and stand-in USB devices, driven by the page and
  by Retroid-style UDP packets at the same time. Every HID report checked out,
  as did refusing foreign websites and letting go of a drag when a phone drops.
  Not yet run on the Pico itself.

Worth checking on the real thing:

- UNLOCK's timing (wake, Space, wait, type) on your lock screen.
- UNLOCK pauses the Retroid for about two seconds while it types.
