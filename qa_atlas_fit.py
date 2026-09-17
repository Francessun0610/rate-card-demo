#!/usr/bin/env python3
"""Verify Atlas presentation shell fit, centering, and dark canvas."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websocket

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROBE = """(() => {
  const deck = document.querySelector('.atlas-deck');
  const wrap = document.querySelector('.atlas-stage-wrap');
  const stage = document.querySelector('.atlas-stage');
  const r = el => el ? el.getBoundingClientRect() : null;
  const cs = el => el ? getComputedStyle(el) : null;
  const deckR = r(deck);
  const stageR = r(stage);
  const wrapR = r(wrap);
  const cx = (stageR.left + stageR.right) / 2;
  const cy = (stageR.top + stageR.bottom) / 2;
  const wcx = (wrapR.left + wrapR.right) / 2;
  const wcy = (wrapR.top + wrapR.bottom) / 2;
  const scale = Number(
    stage?.style.getPropertyValue('--atlas-scale')
      || cs(stage)?.getPropertyValue('--atlas-scale')
      || 0
  );
  return {
    route: document.body.getAttribute('data-route'),
    deckPos: cs(deck)?.position,
    deck: { w: deckR.width, h: deckR.height },
    wrap: { w: wrap?.clientWidth, h: wrap?.clientHeight },
    scale,
    stage: { w: stageR.width, h: stageR.height },
    centeredX: Math.abs(cx - wcx) < 4,
    centeredY: Math.abs(cy - wcy) < 4,
    fitsWidth: stageR.width <= wrapR.width + 1,
    fitsHeight: stageR.height <= wrapR.height + 1,
    bodyBg: cs(document.body).backgroundColor,
    htmlBg: cs(document.documentElement).backgroundColor,
    gnav: cs(document.querySelector('.gnav'))?.display,
    vw: innerWidth,
    vh: innerHeight,
  };
})()"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, *_args):
        return


def probe(url, viewport):
    profile = "/tmp/qa_atlas_fit_profile"
    subprocess.run(["rm", "-rf", profile], check=False)
    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9232",
            f"--user-data-dir={profile}",
            "--headless=new",
            "--remote-allow-origins=*",
            "--no-first-run",
            f"--window-size={viewport[0]},{viewport[1]}",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2.2)
    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9232/json").read())
    ws = websocket.create_connection(
        next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
    )
    mid = 0

    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})

    send("Runtime.enable")
    time.sleep(0.8)
    val = send(
        "Runtime.evaluate",
        {"expression": PROBE, "returnByValue": True},
    )["result"]["value"]
    proc.kill()
    ws.close()
    return val


def check(label, ok, detail):
    print(("PASS" if ok else "FAIL") + f" {label}" + (f" -- {detail}" if detail else ""))
    return ok


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.2)

    passes = 0
    failures = 0
    cases = [
        ("1920x1080", f"http://127.0.0.1:{PORT}/?section=atlas&slide=1", (1920, 1080)),
        ("1440x900", f"http://127.0.0.1:{PORT}/?section=atlas&slide=10", (1440, 900)),
        ("1280x720", f"http://127.0.0.1:{PORT}/?section=atlas&slide=12", (1280, 720)),
        ("narrow", f"http://127.0.0.1:{PORT}/?section=atlas&slide=1", (900, 700)),
    ]

    for label, url, vp in cases:
        print(f"\n== {label} ==")
        val = probe(url, vp)
        print(json.dumps(val, indent=2))
        checks = [
            ("route is atlas", val["route"] == "atlas", val["route"]),
            ("deck is fixed", val["deckPos"] == "fixed", val["deckPos"]),
            ("chrome hidden", val["gnav"] == "none", val["gnav"]),
            ("deck fills viewport width", abs(val["deck"]["w"] - val["vw"]) < 2, val["deck"]["w"]),
            ("deck fills viewport height", abs(val["deck"]["h"] - val["vh"]) < 2, val["deck"]["h"]),
            ("stage centered horizontally", val["centeredX"], val["centeredX"]),
            ("stage centered vertically", val["centeredY"], val["centeredY"]),
            ("stage fits inside wrap", val["fitsWidth"] and val["fitsHeight"], val["stage"]),
            ("scale is proportional", 0 < val["scale"] <= 1, val["scale"]),
            ("scale is not the broken default", val["scale"] < 0.999 or min(val["vw"], val["vh"]) >= 1080, val["scale"]),
            ("body canvas is the presentation canvas", val["bodyBg"] == "rgb(30, 30, 30)", val["bodyBg"]),
            ("html canvas is the presentation canvas", val["htmlBg"] == "rgb(30, 30, 30)", val["htmlBg"]),
        ]
        for name, ok, detail in checks:
            if check(name, ok, detail):
                passes += 1
            else:
                failures += 1

    server.shutdown()
    print(f"\n{passes} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
