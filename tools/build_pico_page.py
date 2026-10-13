#!/usr/bin/env python3
"""Compress www/index.html for the Pico: writes pico/www/index.html.gz.

The Pico can't compress anything itself, so it serves this pre-made copy
(about 12 KB instead of 38 KB). Run it after changing www/index.html, then
copy pico/www/index.html.gz to CIRCUITPY/www/.

    python3 tools/build_pico_page.py
"""
import gzip
import os

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
src = os.path.join(root, "www", "index.html")
dst = os.path.join(root, "pico", "www", "index.html.gz")
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(src, "rb") as f:
    data = f.read()
# mtime=0 so the same page always gives the same bytes (clean git diffs).
with open(dst, "wb") as f:
    f.write(gzip.compress(data, 9, mtime=0))
print(f"{len(data)} -> {os.path.getsize(dst)} bytes: {os.path.relpath(dst, root)}")
