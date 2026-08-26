from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    kind: str = "rss"
    homepage: str = ""
    accent: str = "#666666"
    max_items: int = 25


# Direct publisher feeds/pages are the reliable core. Google News is kept as a
# supplemental discovery source so it can surface additional London publishers
# without making the whole site dependent on Google's undocumented feed format.
SOURCES = [
    Source(
        name="Global News London",
        url="https://globalnews.ca/london/feed",
        homepage="https://globalnews.ca/london/",
        accent="#0088ff",
    ),
    Source(
        name="CBC News London",
        url="https://www.cbc.ca/webfeed/rss/rss-canada-london",
        homepage="https://www.cbc.ca/news/canada/london",
        accent="#ff383c",
    ),
    Source(
        name="London Free Press",
        url="https://lfpress.com/feed",
        homepage="https://lfpress.com/",
        accent="#6155f5",
    ),
    Source(
        name="CTV News",
        url="https://www.ctvnews.ca/london/",
        kind="page",
        homepage="https://www.ctvnews.ca/london/",
        accent="#6155f5",
        max_items=25,
    ),
    Source(
        name="106.9 The X",
        url="https://www.1069thex.com/category/news-home-page/feed/",
        homepage="https://www.1069thex.com/",
        accent="#ff8d28",
    ),
    Source(
        name="City of London Newsroom",
        url="https://london.ca/newsroom",
        kind="page",
        homepage="https://london.ca/newsroom",
        accent="#cb30e0",
        max_items=20,
    ),
    Source(
        name="London Police Service",
        url="https://www.londonpolice.ca/news/authors/london-police-service",
        kind="page",
        homepage="https://www.londonpolice.ca/news/authors/london-police-service",
        accent="#0088ff",
        max_items=25,
    ),
    Source(
        name="London Fire Department",
        url="https://news.google.com/rss/search?q=site:https://x.com/LdnOntFire+when:7d&hl=en-CA&gl=CA&ceid=CA:en",
        homepage="https://x.com/LdnOntFire",
        accent="#ff383c",
    ),
    Source(
        name="104.7 Heart FM",
        url="https://www.heartfm.ca/news/local-news/feed.xml",
        homepage="https://www.heartfm.ca/news/local-news/",
        accent="#ff2d55",
        max_items=30,
    ),
    Source(
        name="Google News London Discovery",
        url="https://news.google.com/rss/topics/CAAqHAgKIhZDQklTQ2pvSWJHOWpZV3hmZGpJb0FBUAE/sections/CAQiTkNCSVNORG9JYkc5allXeGZkakpDRUd4dlkyRnNYM1l5WDNObFkzUnBiMjV5Q2hJSUwyMHZNR0l4ZERGNkNnb0lMMjB2TUdJeGRERW9BQSowCAAqLAgKIiZDQklTRmpvSWJHOWpZV3hmZGpKNkNnb0lMMjB2TUdJeGRERW9BQVABUAE?hl=en-CA&gl=CA&ceid=CA:en",
        kind="google_topic",
        homepage="https://news.google.com/",
        accent="#0088ff",
        max_items=60,
    ),
]
