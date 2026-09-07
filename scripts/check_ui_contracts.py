#!/usr/bin/env python3
"""Fail CI when Forest City News UI invariants regress.

This checks both the visual design contracts and the frontend structure that those
styles depend on. The Svelte app must preserve the established Forest City News
shell/component class names instead of replacing them with a parallel generic UI.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_CSS = ROOT / "public" / "ui-guidelines.css"
FEED_CSS = ROOT / "src" / "styles" / "feed-scope.css"
SVELTE_CSS = ROOT / "src" / "styles" / "svelte-app.css"
NAV_TRANSITIONS = ROOT / "public" / "navigation-transitions.css"
PACKAGE_JSON = ROOT / "package.json"
APP_HTML = ROOT / "src" / "app.html"
ICON = ROOT / "src" / "lib" / "components" / "Icon.svelte"
LAYOUT = ROOT / "src" / "routes" / "+layout.svelte"
HOME = ROOT / "src" / "routes" / "+page.svelte"
CARD = ROOT / "src" / "lib" / "components" / "NewsCard.svelte"
SECTIONS = ROOT / "src" / "routes" / "sections" / "+page.svelte"
SEARCH = ROOT / "src" / "routes" / "search" / "+page.svelte"
READ_LATER = ROOT / "src" / "routes" / "read-later" / "+page.svelte"
SETTINGS = ROOT / "src" / "routes" / "settings" / "+page.svelte"

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


def require_tokens(text: str, tokens: tuple[str, ...], label: str) -> None:
    for token in tokens:
        require(token in text, f"{label} is missing {token!r}")


def main() -> None:
    ui = UI_CSS.read_text(encoding="utf-8")
    feed = FEED_CSS.read_text(encoding="utf-8")
    svelte_css = SVELTE_CSS.read_text(encoding="utf-8")
    nav_transitions = NAV_TRANSITIONS.read_text(encoding="utf-8")
    package_json = PACKAGE_JSON.read_text(encoding="utf-8")
    app_html = APP_HTML.read_text(encoding="utf-8")
    icon = ICON.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    card = CARD.read_text(encoding="utf-8")
    sections = SECTIONS.read_text(encoding="utf-8")
    search = SEARCH.read_text(encoding="utf-8")
    read_later = READ_LATER.read_text(encoding="utf-8")
    settings = SETTINGS.read_text(encoding="utf-8")

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

    require("border: 1px solid var(--ui-border)" not in ui, "persistent control outlines returned")
    require("border: 1px solid var(--ui-selected-border)" not in ui, "selected segment outline returned")

    require_tokens(app_html, (
        "smart-features.css",
        "family=Inter:wght@400;500;600;700;800",
    ), "app head")

    require('"@lucide/svelte": "1.42.0"' in package_json, "Lucide must be bundled locally with the Svelte app")
    require("from '@lucide/svelte'" in icon, "shared icon component must use bundled Lucide")

    require_tokens(svelte_css, (
        "--minimum-ui-type: 14px;",
        "font-size: max(var(--minimum-ui-type), 1em) !important;",
        ".lucide-icon",
    ), "Svelte UI styling")
    require("view-transition-name" not in svelte_css, "route view-transition name returned")
    require("navigation: none" in nav_transitions, "cross-document view transitions must stay disabled")

    require_tokens(layout, (
        'class="site-header"',
        "site-header-home",
        'class="brand brand-news"',
        'class="mobile-tab-bar svelte-mobile-tab-bar"',
        'class="mobile-tab-indicator"',
        "--mobile-tab-count:5",
        "Icon name=\"search\"",
        "Icon name=\"settings\"",
    ), "app shell")
    require("onNavigate" not in layout, "Svelte route transition hook returned")
    require("startViewTransition" not in layout, "browser route crossfade returned")
    tab_count = layout.count('class="mobile-tab"') + layout.count('class="mobile-tab mobile-home-tab"')
    require(tab_count == 5, f"mobile navigation must contain exactly five tab links, found {tab_count}")
    require("app-tab-bar" not in layout, "temporary generic Svelte tab bar returned")

    require_tokens(home, (
        'class="home-page card-home editorial-home"',
        "card-filter-wrap",
        "feed-scope-switch",
        "section-tabs",
        "editorial-front",
        "editorial-front-grid editorial-carousel-ready",
        "editorial-carousel-viewport",
        "editorial-carousel-track",
        "editorial-carousel-slide",
        "editorial-carousel-dots",
        "news-card-grid",
        "story-date-heading",
    ), "home page")
    require("home-masthead" not in home, "temporary serif migration masthead returned")

    require_tokens(card, (
        "card-${variant}",
        'class="news-card-media"',
        'class="news-card-photo"',
        'class="news-card-body"',
        'class="news-card-footer"',
        'class="news-card-save"',
        "card-source-mark",
        "<Icon name=\"bookmark\"",
    ), "story card")
    require("svelte-news-card" not in card, "temporary generic Svelte story card returned")

    require_tokens(sections, (
        "combined-directory-page",
        "directory-tabs",
        "section-directory-grid",
        "source-preference-list",
        "source-switch-input",
        "Icon name={iconFor(category)}",
    ), "sections page")
    require_tokens(search, (
        "directory-page search-page",
        "search-page-field-refined",
        "archive-search-controls",
        "archive-scope-switch",
        "archive-search-results",
        "<Icon name=\"search\"",
    ), "search page")
    require_tokens(read_later, (
        "read-later-page",
        "read-later-shell",
        "read-later-grid",
        "read-later-empty",
        "<Icon name=\"bookmark\"",
    ), "Read Later page")
    require_tokens(settings, (
        "settings-page",
        "settings-shell",
        "settings-segmented",
        "accent-choice",
        "settings-switch-track",
        "<Icon name=\"check\"",
    ), "settings page")

    light_segment_fill = (242, 242, 247)
    light_muted = (108, 108, 112)
    dark_segment_fill = (28, 28, 30)
    dark_muted = (174, 174, 178)
    require(contrast(light_muted, light_segment_fill) >= 4.5, "light inactive segment text is below 4.5:1")
    require(contrast(dark_muted, dark_segment_fill) >= 4.5, "dark inactive segment text is below 4.5:1")

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

    print("UI contracts passed: 14px type floor, bundled Lucide, carousel, no route fades, visual structure, controls, and contrast are valid.")


if __name__ == "__main__":
    main()
