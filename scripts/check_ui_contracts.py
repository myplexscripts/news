#!/usr/bin/env python3
"""Fail CI when Forest City News UI invariants regress.

This intentionally checks the design contracts that should survive later visual work:
- 44px controls and minimum touch targets
- concentric 22px / 3px / 19px pill radii
- no persistent outlines on controls
- no shared Liquid Glass outside the mobile navigation
- at least 4.5:1 label contrast in both themes for every accent colour
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_CSS = ROOT / "public" / "ui-guidelines.css"
FEED_CSS = ROOT / "src" / "styles" / "feed-scope.css"

LIGHT_ACCENTS = {
    "red": (255, 56, 60),
    "orange": (255, 141, 40),
    "yellow": (255, 204, 0),
    "green": (52, 199, 89),
    "mint": (0, 200, 179),
    "teal": (0, 195, 208),
    "cyan": (0, 192, 232),
    "blue": (0, 136, 255),
    "indigo": (97, 85, 245),
    "purple": (203, 48, 224),
    "pink": (255, 45, 85),
    "brown": (172, 127, 94),
}

DARK_ACCENTS = {
    "red": (255, 66, 69),
    "orange": (255, 146, 48),
    "yellow": (255, 214, 0),
    "green": (48, 209, 88),
    "mint": (0, 218, 195),
    "teal": (0, 210, 224),
    "cyan": (60, 211, 254),
    "blue": (0, 145, 255),
    "indigo": (109, 124, 255),
    "purple": (219, 52, 242),
    "pink": (255, 55, 95),
    "brown": (183, 138, 102),
}


def channel(value: int) -> float:
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (channel(value) for value in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def mix(foreground: tuple[int, int, int], background: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(foreground[i] * amount + background[i] * (1 - amount)) for i in range(3))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"UI contract failed: {message}")


def main() -> None:
    ui = UI_CSS.read_text(encoding="utf-8")
    feed = FEED_CSS.read_text(encoding="utf-8")

    required_css = (
        "--ui-control-height: 44px;",
        "--ui-touch-min: 44px;",
        "--ui-control-radius: 22px;",
        "--ui-control-inset: 3px;",
        "--ui-inner-radius: calc(var(--ui-control-radius) - var(--ui-control-inset));",
        "--ui-accent-text: color-mix(in srgb, var(--accent) 45%, black);",
        "--ui-accent-text: color-mix(in srgb, var(--accent) 60%, white);",
    )
    for token in required_css:
        require(token in ui, f"missing required UI token: {token}")

    require("Shared Liquid Glass material" not in feed, "legacy shared Liquid Glass block returned")
    require(".mobile-tab-bar" in ui and "backdrop-filter: blur(34px)" in ui, "mobile nav Liquid Glass is missing")

    # Persistent outlines and borders are intentionally absent from flat controls.
    require("border: 1px solid var(--ui-border)" not in ui, "persistent control outlines returned")
    require("border: 1px solid var(--ui-selected-border)" not in ui, "selected segment outline returned")

    # Inactive labels remain readable on the flat segmented-control backgrounds.
    light_segment_fill = (242, 242, 247)
    light_muted = (108, 108, 112)
    dark_segment_fill = (28, 28, 30)
    dark_muted = (174, 174, 178)
    require(contrast(light_muted, light_segment_fill) >= 4.5, "light inactive segment text is below 4.5:1")
    require(contrast(dark_muted, dark_segment_fill) >= 4.5, "dark inactive segment text is below 4.5:1")

    # Action and selected labels use accent-aware foregrounds that remain readable.
    light_action_fill = (242, 242, 247)
    light_selected_fill = (255, 255, 255)
    dark_action_fill = (44, 44, 46)
    dark_selected_fill = (58, 58, 60)

    for name, accent in LIGHT_ACCENTS.items():
        text = mix(accent, (0, 0, 0), 0.45)
        action_ratio = contrast(text, light_action_fill)
        selected_ratio = contrast(text, light_selected_fill)
        require(action_ratio >= 4.5, f"light {name} action text is only {action_ratio:.2f}:1")
        require(selected_ratio >= 4.5, f"light {name} selected text is only {selected_ratio:.2f}:1")

    for name, accent in DARK_ACCENTS.items():
        text = mix(accent, (255, 255, 255), 0.60)
        action_ratio = contrast(text, dark_action_fill)
        selected_ratio = contrast(text, dark_selected_fill)
        require(action_ratio >= 4.5, f"dark {name} action text is only {action_ratio:.2f}:1")
        require(selected_ratio >= 4.5, f"dark {name} selected text is only {selected_ratio:.2f}:1")

    print("UI contracts passed: pill geometry, nav-only glass, flat controls, and label contrast are valid.")


if __name__ == "__main__":
    main()
