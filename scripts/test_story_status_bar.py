from __future__ import annotations

import re
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

import prepare_frontend

ROOT = Path(__file__).resolve().parents[1]


def channel_distance(left: str, right: str) -> int:
    parse = lambda value: tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
    a = parse(left)
    b = parse(right)
    return sum(abs(a[index] - b[index]) for index in range(3))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "hero.png"
        image = Image.new("RGB", (120, 100), (220, 35, 30))
        # The sampled top 16% is blue while the other 84% is red. A correct sampler
        # must stay close to the blue band instead of averaging the whole image.
        for y in range(16):
            for x in range(120):
                image.putpixel((x, y), (24, 104, 184))
        image.save(path)

        colour = prepare_frontend.representative_top_colour(path)
        assert re.fullmatch(r"#[0-9a-f]{6}", colour), colour
        assert channel_distance(colour, "#1868b8") < 30, colour
        assert channel_distance(colour, "#dc231e") > 200, colour

        handler = partial(QuietHandler, directory=temp_dir)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote_url = f"http://127.0.0.1:{server.server_port}/hero.png"
            remote_colour = prepare_frontend.representative_top_colour_url(remote_url)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert re.fullmatch(r"#[0-9a-f]{6}", remote_colour), remote_colour
        assert channel_distance(remote_colour, "#1868b8") < 30, remote_colour

    css = (ROOT / "public" / "story-status-bar.css").read_text(encoding="utf-8")
    js = (ROOT / "public" / "story-status-bar.js").read_text(encoding="utf-8")
    app = (ROOT / "src" / "app.html").read_text(encoding="utf-8")

    assert "standalone-webapp.story-status-coloured" in css
    assert "height: env(safe-area-inset-top, 0px);" in css
    assert "background: var(--story-status-colour);" in css
    assert "body:not(:has(.svelte-article-page)) .site-header {" in css
    assert "padding-top: env(safe-area-inset-top, 0px) !important;" in css
    assert "article-cover-media" in css
    assert "linear-gradient(" not in css
    assert "mask-image" not in css
    assert "filter: blur" not in css
    assert "transition:" not in css

    assert "navigator.standalone" in js
    assert "display-mode: standalone" in js
    assert "hero_top_colour" in js
    assert 'meta[name="theme-color"]' in js
    assert "setSystemThemeColour" in js
    assert "restoreSystemThemeColour" in js
    assert "background-color" in js

    assert "story-status-bar.css?v=20260908-4" in app
    assert "story-status-bar.js?v=20260908-4" in app

    print("Story solid status colour, remote sampling, theme colour, and safe-area contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
