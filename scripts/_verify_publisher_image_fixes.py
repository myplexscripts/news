from __future__ import annotations

from bs4 import BeautifulSoup

import fetch_news as f


CASES = [
    (
        "CBC burnout",
        "CBC News London",
        "https://www.cbc.ca/news/canada/london/burnout-isn-t-new-how-18th-century-farming-set-the-stage-for-modern-worker-exhaustion-9.7328400",
    ),
    (
        "CBC buses",
        "CBC News London",
        "https://www.cbc.ca/news/canada/london/here-s-what-you-need-to-know-about-london-s-new-centre-running-bus-lanes-9.7334426",
    ),
    (
        "CTV advocate",
        "CTV News Canada",
        "https://www.ctvnews.ca/canada/article/indigenous-advocate-leads-calm-environment-in-program-for-customers-security-guards/",
    ),
    (
        "Globe floods",
        "The Globe and Mail",
        "https://www.theglobeandmail.com/canada/article-cape-breton-nova-scotia-floods-emergency-roads-power/",
    ),
]


def inspect_case(label: str, source_name: str, url: str) -> dict[str, object]:
    raw, final = f.fetch_html(url)
    soup = BeautifulSoup(raw, "html.parser")
    ld = f.article_json_ld(soup)
    candidates = f.collect_image_candidates(soup, final, ld)
    lead = candidates[0]["url"] if candidates else ""
    root, selector = f.choose_article_root(soup, source_name)
    blocks, stats, method = f.extract_dom_blocks(soup, final, source_name, label, lead)
    dom_images = [block for block in blocks if block.get("type") == "image"]
    ctv_images: list[dict] = []
    if f.is_ctv_source(source_name):
        ctv_blocks, _ = f.extract_ctv_embedded_blocks(soup, label, final)
        ctv_images = [block for block in ctv_blocks if block.get("type") == "image"]
    print(
        "LIVE",
        label,
        "lead=",
        bool(lead),
        "candidates=",
        len(candidates),
        "root=",
        selector,
        "dom_images=",
        len(dom_images),
        "ctv_embedded_images=",
        len(ctv_images),
        "method=",
        method,
        "rejected=",
        stats.get("images_rejected", 0),
    )
    for image in dom_images:
        print("  DOM", image.get("url"), "|", image.get("caption", ""))
    for image in ctv_images:
        print("  CTV", image.get("url"), "|", image.get("caption", ""))
    return {
        "candidates": candidates,
        "lead": lead,
        "root": root,
        "selector": selector,
        "dom_images": dom_images,
        "ctv_images": ctv_images,
        "method": method,
    }


def main() -> int:
    results = {label: inspect_case(label, source, url) for label, source, url in CASES}

    burnout = results["CBC burnout"]
    assert burnout["lead"], "CBC burnout hero image should survive validation"
    assert any("1788290677516" in item["url"] for item in burnout["candidates"]), "CBC burnout editorial image was not recovered"

    buses = results["CBC buses"]
    bus_images = buses["dom_images"]
    assert len(bus_images) >= 3, f"Expected the three CBC bus-lane article photos, got {len(bus_images)}"
    assert all("i.cbc.ca/ais/" in image["url"] for image in bus_images), "CBC srcset URL was corrupted"

    ctv = results["CTV advocate"]
    assert len(ctv["ctv_images"]) >= 2, "CTV Arc/Fusion story images were not recovered"

    globe = results["Globe floods"]
    root = globe["root"]
    assert root is not None and root.get("id") == "content-gate", f"Globe chose broad root {globe['selector']}"
    assert len(globe["dom_images"]) >= 1, "Globe inline body image was not recovered"

    print("LIVE publisher image verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
