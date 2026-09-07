from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def require(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Missing built {label}: {path.relative_to(ROOT)}")


def main() -> int:
    try:
        require(DIST / "index.html", "home page")
        require(DIST / "data" / "app-feed.json", "app feed")
        require(DIST / "sw.js", "service worker")
        require(DIST / "manifest.webmanifest", "web app manifest")

        story_files = list((DIST / "data" / "stories").glob("*.json"))
        if not story_files:
            raise RuntimeError("No per-story JSON files were copied into dist/data/stories")

        css_files = list((DIST / "_app" / "immutable" / "assets").glob("*.css"))
        if not css_files:
            raise RuntimeError("No SvelteKit CSS bundle was generated")

        feed = json.loads((DIST / "data" / "app-feed.json").read_text(encoding="utf-8"))
        if not isinstance(feed.get("stories"), list) or not feed["stories"]:
            raise RuntimeError("Built app feed contains no stories")

        html = (DIST / "index.html").read_text(encoding="utf-8")
        if "_app/immutable" not in html:
            raise RuntimeError("Home page does not reference the SvelteKit app bundle")

        print(
            f"Pages smoke test passed: {len(feed['stories'])} feed stories, "
            f"{len(story_files)} story files, {len(css_files)} CSS bundles"
        )
        return 0
    except Exception as exc:
        print(f"Pages smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
