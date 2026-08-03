#!/usr/bin/env python
"""Serve the generated graph org-chart site from localhost."""
from __future__ import annotations

import argparse
import http.server
import socketserver
from functools import partial
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="local_data/organization/org_chart_site")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    directory = Path(args.directory).resolve()
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"Serving graph org-chart site from {directory}")
        print(f"Open http://{args.host}:{args.port}/index.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
