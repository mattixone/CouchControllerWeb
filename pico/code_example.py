# How couch_web fits into code.py: three additions to the existing firmware.
# (The real code.py, with these already in, is kept off GitHub; see README.)

# 1. Import it, guarded, so a missing or broken couch_web.py can never stop
#    the Retroid link:
try:
    import couch_web
except Exception as exc:
    couch_web = None
    print("Phone remote unavailable:", exc)


# 2. Start it once Wi-Fi is up, reusing the HID objects and helpers code.py
#    already has (move_mouse splits big moves; do_power is the Win+X sequence):
def start_phone_remote(pool):
    if couch_web is None or not getattr(config, "WEB_REMOTE", True):
        return None
    try:
        return couch_web.CouchWeb(
            pool, kbd, layout, mouse, consumer,
            move_mouse=move_mouse, do_power=do_power,
            unlock_secret=str(getattr(config, "UNLOCK_PIN", "") or ""),
            allow_power=getattr(config, "WEB_POWER", True),
        )
    except Exception as exc:
        print("Phone remote failed to start:", exc)
        return None


# 3. Poll it at the top of the UDP receive loop. It returns at once unless
#    ~4 ms have passed and never blocks, so the Retroid isn't held up:
#
#     web = start_phone_remote(pool)
#     while True:
#         if web is not None:
#             try:
#                 web.poll()
#             except Exception as exc:
#                 print("phone remote error:", exc)
#         ...existing recvfrom_into / handle()...
