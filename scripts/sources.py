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
        name="Global News London",
        url="https://globalnews.ca/london/feed",
        homepage="https://globalnews.ca/london/",
        accent="#0088FF",
    ),
    Source(
        name="CBC News London",
        url="https://www.cbc.ca/webfeed/rss/rss-canada-london",
        homepage="https://www.cbc.ca/news/canada/london",
        accent="#FF383C",
    ),
    Source(
        name="London Free Press",
        url="https://lfpress.com/feed",
        homepage="https://lfpress.com/",
        accent="#6155F5",
    ),
    Source(
        name="CTV News",
        url="https://news.google.com/rss/search?q=site:https://www.ctvnews.ca/london/+when:7d&hl=en-CA&gl=CA&ceid=CA:en",
        homepage="https://www.ctvnews.ca/london/",
        accent="#6155F5",
    ),
    Source(
        name="106.9 The X",
        url="https://www.1069thex.com/category/news-home-page/feed/",
        homepage="https://www.1069thex.com/",
        accent="#FF8D28",
    ),
    Source(
        name="City of London Newsroom",
        url="https://news.google.com/rss/search?q=site:https://london.ca/newsroom+when:7d&hl=en-CA&gl=CA&ceid=CA:en",
        homepage="https://london.ca/newsroom",
        accent="#CB30E0",
    ),
    Source(
        name="London Police Service",
        url="https://news.google.com/rss/search?q=site:https://x.com/lpsmediaoffice+when:7d&hl=en-CA&gl=CA&ceid=CA:en",
        homepage="https://x.com/lpsmediaoffice",
        accent="#0088FF",
    ),
    Source(
        name="London Fire Department",
        url="https://news.google.com/rss/search?q=site:https://x.com/LdnOntFire+when:7d&hl=en-CA&gl=CA&ceid=CA:en",
        homepage="https://x.com/LdnOntFire",
        accent="#FF383C",
    ),
]
