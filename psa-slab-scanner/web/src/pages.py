"""Turn the page templates into the standalone pages in web/.

    python3 web/src/pages.py overview             # after web/src/overview/build_page.py has written slabrail.html
    python3 web/src/pages.py viewer  MESH_DIR     # MESH_DIR holds model.json + model.bin from viewer/export_meshes.py
    python3 web/src/pages.py replay  REPLAY_DIR   # REPLAY_DIR holds replay.json from replay/record.py

Each page is wrapped in a plain HTML document (charset, viewport, a small reset) so it opens straight from disk.
"""

import base64
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
WEB = SRC.parent

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""
TAIL = "\n</body>\n</html>\n"


def wrap(body: str, name: str) -> Path:
    body = "\n".join(line for line in body.splitlines() if 'name="claude:viewport-fit-sides"' not in line)
    out = WEB / name
    out.write_text(HEAD + body + TAIL)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    return out


def main(kind: str, data_dir: str | None = None) -> None:
    if kind == "overview":
        wrap((SRC / "overview" / "slabrail.html").read_text(), "slabrail.html")
    elif kind == "viewer":
        d = Path(data_dir)
        t = (SRC / "viewer" / "template.html").read_text()
        t = t.replace("/*MODEL_JSON*/null", (d / "model.json").read_text().strip())
        t = t.replace("/*MODEL_B64*/", base64.b64encode((d / "model.bin").read_bytes()).decode())
        wrap(t, "slabrail_3d.html")
    elif kind == "replay":
        t = (SRC / "replay" / "template.html").read_text()
        wrap(t.replace("/*DATA*/null", (Path(data_dir) / "replay.json").read_text().strip()), "slabrail_replay.html")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(*sys.argv[1:])
