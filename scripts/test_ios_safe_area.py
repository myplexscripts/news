from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    css = (ROOT / "public" / "ios-safe-area.css").read_text(encoding="utf-8")
    app = (ROOT / "src" / "app.html").read_text(encoding="utf-8")
    prepare = (ROOT / "scripts" / "prepare_frontend.py").read_text(encoding="utf-8")

    # No article-derived colour strip remains anywhere in the app shell.
    assert "ios-status-strip" not in app
    assert "story-status-bar" not in app
    assert "hero_top_colour" not in prepare
    assert "story-status-coloured" not in css
    assert "background-color: var(--story-status-colour)" not in css

    # Installed app chrome stays below the system safe area.
    assert "html.standalone-webapp .site-header" in css
    assert "padding-top: var(--standalone-status-height) !important;" in css
    assert "html.standalone-webapp.story-route .site-header .header-inner" in css

    # Editorial media begins at the physical top of the viewport, behind iOS
    # system chrome, while preserving the tuned lower edge on mobile.
    assert "html.standalone-webapp.story-route .article-cover-media" in css
    assert "top: 0 !important;" in css
    assert "height: 78svh !important;" in css
    assert "height: 70svh !important;" in css

    assert "ios-safe-area.css?v=20260908-1" in app
    assert "story-status-bar.css" not in app
    assert "story-status-bar.js" not in app

    print("iOS safe-area and full-bleed editorial image contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
