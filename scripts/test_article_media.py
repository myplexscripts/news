from __future__ import annotations

from enrich_article_media import extract_dom_media, media_block, merge_media, safe_embed_url


def test_dom_audio_is_preserved() -> None:
    raw = """
    <article>
      <p>LISTEN | Hear the full interview with the researcher below.</p>
      <audio controls><source src="/media/interview.mp3" type="audio/mpeg"></audio>
      <p>The interview continued with a discussion of severe-weather research and community resilience.</p>
    </article>
    """
    media = extract_dom_media(raw, "https://example.test/story")
    assert len(media) == 1
    anchor, block = media[0]
    assert "full interview" in anchor
    assert block["media_type"] == "audio"
    assert block["url"] == "https://example.test/media/interview.mp3"


def test_dom_video_keeps_poster() -> None:
    raw = """
    <article>
      <p>WATCH | Video from the scene is available below.</p>
      <video controls src="https://media.example.test/report.mp4" poster="/images/poster.jpg"></video>
    </article>
    """
    media = extract_dom_media(raw, "https://example.test/story")
    assert len(media) == 1
    _, block = media[0]
    assert block["media_type"] == "video"
    assert block["poster"] == "https://example.test/images/poster.jpg"


def test_safe_embed_is_preserved_and_unknown_embed_is_rejected() -> None:
    raw = """
    <article>
      <p>WATCH | The publisher included video with this report.</p>
      <iframe src="https://www.youtube.com/embed/abc123" title="Video report"></iframe>
      <iframe src="https://unknown.example.test/embed/123" title="Unknown"></iframe>
    </article>
    """
    media = extract_dom_media(raw, "https://example.test/story")
    assert len(media) == 1
    assert media[0][1]["media_type"] == "embed"
    assert "youtube.com/embed/abc123" in media[0][1]["url"]
    assert safe_embed_url("https://unknown.example.test/embed/123") == ""


def test_media_is_inserted_after_matching_cue() -> None:
    blocks = [
        {"type": "paragraph", "text": "The researcher moved to London to continue his work."},
        {"type": "paragraph", "text": "LISTEN | Seth Guikema on why he's continuing his research in Canada:"},
        {"type": "paragraph", "text": "The interview then returned to severe weather and risk analysis."},
    ]
    block = media_block("https://media.example.test/interview.mp3", "Afternoon Drive interview")
    assert block is not None
    merged, inserted = merge_media(blocks, [("LISTEN | Seth Guikema on why he's continuing his research in Canada:", block)])
    assert inserted == 1
    assert merged[2]["type"] == "media"
    assert merged[2]["media_type"] == "audio"


def test_non_playable_media_link_is_rejected() -> None:
    block = media_block("https://example.test/article", "Listen to the full interview")
    assert block is None


def test_safe_cbc_player_url_can_embed() -> None:
    block = media_block("https://www.cbc.ca/player/play/video/123", "Watch the report")
    assert block is not None
    assert block["media_type"] == "embed"


def main() -> int:
    tests = [
        test_dom_audio_is_preserved,
        test_dom_video_keeps_poster,
        test_safe_embed_is_preserved_and_unknown_embed_is_rejected,
        test_media_is_inserted_after_matching_cue,
        test_non_playable_media_link_is_rejected,
        test_safe_cbc_player_url_can_embed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
