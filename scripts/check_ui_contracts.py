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
APP_HTML = ROOT / "src" / "app.html"
LAYOUT = ROOT / "src" / "routes" / "+layout.svelte"
HOME = ROOT / "src" / "routes" / "+page.svelte"
CARD = ROOT / "src" / "lib" / "components" / "NewsCard.svelte"
SECTIONS = ROOT / "src" / "routes" / "sections" / "+page.svelte"
SEARCH = ROOT / "src" / "routes" / "search" / "+page.svelte"
SETTINGS = ROOT / "src" / "routes" / "settings" / "+page.svelte"
FONT_DIR = ROOT / "src" / "lib" / "fonts"
SMART = ROOT / "public" / "smart-features.css"
GLOBAL = ROOT / "src" / "styles" / "global.css"
POLISH = ROOT / "src" / "styles" / "polish.css"

LIGHT_ACCENTS = {
    "red": (213, 0, 0),
    "orange": (197, 84, 0),
    "yellow": (255, 214, 0),
    "green": (58, 134, 61),
    "teal": (0, 133, 120),
    "blue": (24, 121, 206),
    "indigo": (57, 73, 171),
    "deep-purple": (81, 45, 168),
    "purple": (142, 36, 170),
    "pink": (230, 23, 93),
    "brown": (109, 76, 65),
}

DARK_ACCENTS = {
    "red": (255, 38, 38),
    "orange": (255, 109, 0),
    "yellow": (253, 216, 53),
    "green": (76, 175, 80),
    "teal": (0, 148, 133),
    "blue": (30, 136, 229),
    "indigo": (112, 126, 207),
    "deep-purple": (144, 114, 217),
    "purple": (191, 86, 219),
    "pink": (236, 63, 122),
    "brown": (166, 121, 105),
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
    app_html = APP_HTML.read_text(encoding="utf-8")
    styles = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    card = CARD.read_text(encoding="utf-8")
    sections = SECTIONS.read_text(encoding="utf-8")
    search = SEARCH.read_text(encoding="utf-8")
    settings = SETTINGS.read_text(encoding="utf-8")
    global_css = GLOBAL.read_text(encoding="utf-8")
    polish = POLISH.read_text(encoding="utf-8")
    smart = SMART.read_text(encoding="utf-8")

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

    require_tokens(styles, (



    ), "app head")

    require_tokens(styles, ("smart-features.css", "ui-guidelines.css", "mobile-nav-stable.css", "app-polish.css"), "shared stylesheet entry")
    require_tokens(layout, (
        'class="site-header"',
        "site-header-home",
        'class="brand brand-news"',
        'class="mobile-tab-bar svelte-mobile-tab-bar"',
        'class="mobile-tab-indicator"',
        "--mobile-tab-count: 4",
    ), "app shell")
    tab_count = layout.count('class="mobile-tab"') + layout.count('class="mobile-tab mobile-home-tab"')
    require(tab_count == 4, f"mobile navigation must contain exactly four tab links, found {tab_count}")
    require("app-tab-bar" not in layout, "temporary generic Svelte tab bar returned")

    require_tokens(home, (
        'class="home-page card-home editorial-home"',
        "card-filter-wrap",
        "feed-scope-switch",
        "section-tabs",
        "category-pill-strip",
        "categoryIcon",
        "editorial-front",
        "editorial-front-grid",
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
        "card-source-name",
    ), "story card")
    require("card-source-mark" not in card, "publisher logo returned to story cards")
    require("sourceLogoPath" not in card, "story cards still load publisher logos")
    require("svelte-news-card" not in card, "temporary generic Svelte story card returned")

    require_tokens(sections, (
        "combined-directory-page",
        "directory-tabs",
        "section-directory-grid",
        "source-preference-list",
        "source-switch-input",
    ), "sections page")
    require_tokens(search, (
        "directory-page search-page",
        "search-page-field-refined",
        "archive-search-controls",
        "archive-scope-switch",
        "archive-search-results",
    ), "search page")
    require('news-card-save' not in card, "removed bookmark control returned")
    require(not any((ROOT / "src/routes/read-later").glob("+page.*")), "removed bookmark page returned")
    require_tokens(settings, (
        "settings-page",
        "settings-shell",
        "settings-segmented",
        "accent-choice",
        "settings-switch-track",
    ), "settings page")
    require("['deep-purple', 'Deep Purple']" in settings, "Deep Purple accent choice is missing")
    require("['mint', 'Mint']" not in settings and "['cyan', 'Cyan']" not in settings, "retired Mint/Cyan accent choices returned")
    require("html[data-accent='deep-purple'] { --accent: var(--deep-purple); }" in polish, "Deep Purple accent wiring is missing")
    require("html[data-accent='mint']" not in polish and "html[data-accent='cyan']" not in polish, "retired Mint/Cyan accent wiring returned")

    palette_tokens = (
        "--red: #D50000;", "--orange: #C55400;", "--yellow: #FFD600;",
        "--green: #3A863D;", "--teal: #008578;", "--blue: #1879CE;",
        "--indigo: #3949AB;", "--deep-purple: #512DA8;", "--purple: #8E24AA;",
        "--pink: #E6175D;", "--brown: #6D4C41;",
        "--red: #FF2626;", "--orange: #FF6D00;", "--yellow: #FDD835;",
        "--green: #4CAF50;", "--teal: #009485;", "--blue: #1E88E5;",
        "--indigo: #707ECF;", "--deep-purple: #9072D9;", "--purple: #BF56DB;",
        "--pink: #EC3F7A;", "--brown: #A67969;",
    )
    require_tokens(global_css, palette_tokens, "accent palette")
    require_tokens(smart, palette_tokens, "smart-features accent palette")
    require("#FF383C" not in smart and "#34C759" not in smart and "#0088FF" not in smart, "legacy accent palette returned in smart-features")

    require_tokens(global_css, (
        '--font-sans: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;',
        "--type-size-editorial: clamp(2rem, 5vw, 2.5rem);",
        "--type-size-story-title: clamp(1.875rem, 4vw, 2.125rem);",
        "--type-size-section-title: 1.75rem;",
        "--type-size-card-featured: 1.375rem;",
        "--type-size-card: 1.125rem;",
        "--type-size-card-compact: 1rem;",
        "--type-size-body-lg: 1.125rem;",
        "--type-size-body: 1rem;",
        "--type-size-ui: 0.9375rem;",
        "--type-size-secondary: 0.875rem;",
        "--type-size-meta: 0.875rem;",
        "--type-size-label: 0.875rem;",
    ), "typography scale")
    app_polish = (ROOT / "src/styles/app-polish.css").read_text(encoding="utf-8")
    require("../lib/fonts/InterVariable.woff2" in app_polish, "self-hosted Inter variable roman face is missing")
    require("../lib/fonts/InterVariable-Italic.woff2" in app_polish, "self-hosted Inter variable italic face is missing")
    require((FONT_DIR / "InterVariable.woff2").stat().st_size > 300_000, "Inter variable roman font file is missing or truncated")
    require((FONT_DIR / "InterVariable-Italic.woff2").stat().st_size > 300_000, "Inter variable italic font file is missing or truncated")
    require("SIL OPEN FONT LICENSE Version 1.1" in (FONT_DIR / "OFL.txt").read_text(encoding="utf-8"), "Inter OFL licence is missing")

    page_header = (ROOT / "src/lib/components/PageHeader.svelte").read_text(encoding="utf-8")
    require('class="page-heading standard-page-heading"' in page_header, "shared PageHeader component lost canonical classes")
    for route in ("latest", "search", "sections", "settings"):
        page_source = (ROOT / "src/routes" / route / "+page.svelte").read_text(encoding="utf-8")
        require("PageHeader" in page_source, f"{route} page is not using the shared PageHeader")
        require("masthead-label" not in page_source, f"{route} page restored a subtitle label")
        require("page-heading-description" not in page_source, f"{route} page restored a page subtitle")

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

    print("UI contracts passed: visual structure, assets, nav, cards, controls, and contrast are valid.")


if __name__ == "__main__":
    main()
