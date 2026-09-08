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


def luminance(colour: str) -> float:
    value = colour.lstrip("#")
    r, g, b = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


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

        # Near-white and near-black pixels must never win the status colour.
        white_path = Path(temp_dir) / "mostly-white.png"
        white_image = Image.new("RGB", (120, 100), (247, 247, 247))
        for y in range(16):
            for x in range(30):
                white_image.putpixel((x, y), (42, 118, 188))
        white_image.save(white_path)
        white_colour = prepare_frontend.representative_top_colour(white_path)
        assert prepare_frontend.status_colour_allowed(white_colour), white_colour
        assert luminance(white_colour) <= prepare_frontend.STATUS_MAX_LUMINANCE, white_colour
        assert channel_distance(white_colour, "#ffffff") > 100, white_colour

        black_path = Path(temp_dir) / "mostly-black.png"
        black_image = Image.new("RGB", (120, 100), (6, 6, 6))
        for y in range(16):
            for x in range(30):
                black_image.putpixel((x, y), (48, 150, 82))
        black_image.save(black_path)
        black_colour = prepare_frontend.representative_top_colour(black_path)
        assert prepare_frontend.status_colour_allowed(black_colour), black_colour
        assert luminance(black_colour) >= prepare_frontend.STATUS_MIN_LUMINANCE, black_colour
        assert channel_distance(black_colour, "#000000") > 100, black_colour

        assert prepare_frontend.existing_story_colour({"hero_top_colour": "#ffffff"}) == ""
        assert prepare_frontend.existing_story_colour({"hero_top_colour": "#000000"}) == ""

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

    # The status strip is an opaque page element that starts behind the system
    # status bar but scrolls away with the document. It must never be viewport-fixed.
    assert "#ios-status-strip" in css
    assert "position: absolute;" in css
    assert "position: fixed;" not in css
    assert "z-index: 2147483000;" in css
    assert "background-color: var(--story-status-colour) !important;" in css
    assert "background-image: none !important;" in css
    assert "opacity: 1 !important;" in css
    assert "mix-blend-mode: normal !important;" in css
    assert "::before" not in css
    assert ":has(" not in css
    assert "linear-gradient(" not in css
    assert "transition:" not in css

    # Safe-area spacing still applies at every standalone viewport width.
    assert "html.standalone-webapp .site-header {" in css
    assert "padding-top: var(--standalone-status-height) !important;" in css
    assert "html.standalone-webapp.story-route .site-header .header-inner" in css
    assert "article-cover-media" in css

    # JS measures the iOS inset, provides a landscape fallback, and paints the
    # real page strip. It must not pin the article colour into iOS theme chrome.
    assert "navigator.standalone" in js
    assert "display-mode: standalone" in js
    assert "--standalone-status-height" in js
    assert "const fallback = isiPhone ? 59 : isiPad ? 24 : 0;" in js
    assert "story-route" in js
    assert "hero_top_colour" in js
    assert "statusStrip.style.setProperty('background-color', value, 'important')" in js
    assert 'meta[name="theme-color"]' not in js
    assert "setSystemThemeColour" not in js

    # The strip exists before Svelte renders and this release is cache-busted.
    assert '<div id="ios-status-strip" aria-hidden="true"></div>' in app
    assert "story-status-bar.css?v=20260908-6" in app
    assert "story-status-bar.js?v=20260908-6" in app
    assert "standalone-status-height" in app

    print("Scrolling opaque iOS status strip and non-extreme colour contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
