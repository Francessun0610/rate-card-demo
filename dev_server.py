"""Loopback-only static development server with deterministic cache headers."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FINGERPRINT_FILES = ("index.html", "v2.css", "v2.js")


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git_fingerprint() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return f"{commit}{'-dirty' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def runtime_fingerprint() -> str:
    assets = ",".join(
        f"{name}={file_digest(ROOT / name)}" for name in FINGERPRINT_FILES
    )
    return f"{assets},git={git_fingerprint()}"


class DevelopmentHandler(SimpleHTTPRequestHandler):
    """Serve the checked-out source without reusing browser cache entries."""

    # SECURITY-REVIEW: This development server is restricted to loopback and
    # serves only the fixed repository root, never a user-selected directory.
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-RCM-Entry", "index.html")
        self.send_header("X-RCM-Runtime", runtime_fingerprint())
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DevelopmentHandler)
    print(f"Serving {ROOT} at http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
