from __future__ import annotations

import re
import tempfile
from pathlib import Path

from PIL import Image

import prepare_frontend

ROOT = Path(__file__).resolve().parents[1]


def channel_distance(left: str, right: str) -> int:
    parse = lambda value: tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
    a = parse(left)
    b = parse(right)
    return sum(abs(a[index] - b[index]) for index in range(3))


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

    css = (ROOT / "public" / "story-status-bar.css").read_text(encoding="utf-8")
    js = (ROOT / "public" / "story-status-bar.js").read_text(encoding="utf-8")
    app = (ROOT / "src" / "app.html").read_text(encoding="utf-8")

    assert "standalone-webapp" in css
    assert "height: env(safe-area-inset-top, 0px);" in css
    assert "background: var(--story-status-colour, var(--bg));" in css
    assert "body:not(:has(.svelte-article-page)) .site-header {" in css
    assert "padding-top: env(safe-area-inset-top, 0px) !important;" in css
    assert "article-cover-media" in css
    assert "linear-gradient(" not in css
    assert "mask-image" not in css
    assert "filter: blur" not in css
    assert "navigator.standalone" in js
    assert "display-mode: standalone" in js
    assert "hero_top_colour" in js
    assert "story-status-bar.css" in app
    assert "story-status-bar.js" in app

    print("Story solid status colour and standalone safe-area contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
