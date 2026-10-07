# How to fit couch_web into code.py. Your real code.py already sets up
# Wi-Fi, mDNS and the HID devices for the Retroid; reuse those objects
# rather than creating a second set, and add the three marked lines.

import time

import mdns
import socketpool
import usb_hid
import wifi
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from couch_web import CouchWeb                                   # <-- 1

# --- existing setup (yours will differ) ---
keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)
mouse = Mouse(usb_hid.devices)
consumer = ConsumerControl(usb_hid.devices)

# wifi.radio.connect(...) happens automatically from CIRCUITPY_WIFI_SSID /
# CIRCUITPY_WIFI_PASSWORD in settings.toml.
while not wifi.radio.connected:
    time.sleep(0.5)

dns = mdns.Server(wifi.radio)
dns.hostname = "couchcommander"                 # -> couchcommander.local
dns.advertise_service(service_type="_http", protocol="_tcp", port=80)

pool = socketpool.SocketPool(wifi.radio)

web = CouchWeb(pool, mouse, keyboard, layout, consumer)          # <-- 2
web.start()

while True:
    web.poll()                                                   # <-- 3
    # ...existing Retroid server polling goes here. Keep it non-blocking
    # (timeouts of 0 or a few ms) so both stay responsive.
    time.sleep(0.001)
