from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    kind: str = "rss"
    homepage: str = ""
    accent: str = "#666666"
    max_items: int = 25


SOURCES = [
    Source(
        name="CBC London",
        url="https://www.cbc.ca/webfeed/rss/rss-canada-london",
        homepage="https://www.cbc.ca/news/canada/london",
        accent="#d9232e",
    ),
    Source(
        name="CTV News London",
        url="https://london.ctvnews.ca/rss/ctv-news-london-1.1073369",
        homepage="https://london.ctvnews.ca/",
        accent="#2d4a9b",
    ),
    Source(
        name="Global News London",
        url="https://globalnews.ca/london/feed/",
        homepage="https://globalnews.ca/london/",
        accent="#1b4f9b",
    ),
    Source(
        name="London Free Press",
        url="https://lfpress.com/feed",
        homepage="https://lfpress.com/",
        accent="#111111",
    ),
    Source(
        name="City of London",
        url="https://london.ca/newsroom",
        kind="page",
        homepage="https://london.ca/newsroom",
        accent="#6b248f",
        max_items=18,
    ),
    Source(
        name="London Police Service",
        url="https://www.londonpolice.ca/news/",
        kind="page",
        homepage="https://www.londonpolice.ca/news/",
        accent="#1d426f",
        max_items=18,
    ),
]
