from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    kind: str = "rss"
    homepage: str = ""
    accent: str = "#666666"
    max_items: int = 25
    logo: str = ""
    scope: str = "local"


# London remains the core feed. National publishers are collected separately and
# tagged with scope="canada" so the site can offer Local, Canada, and All views
# without weakening the local-news collector or relying on publisher name hacks.
SOURCES = [
    Source(
        name="Global News London",
        logo="images/logos/Global_News.svg",
        url="https://globalnews.ca/london/feed",
        homepage="https://globalnews.ca/london/",
        accent="#0088ff",
    ),
    Source(
        name="CBC News London",
        logo="images/logos/CBC_News_Logo.svg",
        url="https://www.cbc.ca/webfeed/rss/rss-canada-london",
        homepage="https://www.cbc.ca/news/canada/london",
        accent="#ff383c",
    ),
    Source(
        name="London Free Press",
        logo="images/logos/The_London_Free_Press_Logo.svg",
        url="https://lfpress.com/feed",
        homepage="https://lfpress.com/",
        accent="#6155f5",
    ),
    Source(
        name="CTV News London",
        logo="images/logos/CTVNews_horizontal_logo.svg",
        # CTV's legacy London RSS endpoint now redirects to a dead URL. Discover
        # stories from the current London landing page and scrape the first-party
        # /london/article/ pages directly instead.
        url="https://www.ctvnews.ca/london/",
        kind="page",
        homepage="https://www.ctvnews.ca/london/",
        accent="#6155f5",
        max_items=30,
    ),
    Source(
        name="106.9 The X",
        logo="images/logos/1069thex.png",
        url="https://www.1069thex.com/category/news-home-page/feed/",
        homepage="https://www.1069thex.com/",
        accent="#ff8d28",
    ),
    Source(
        name="City of London Newsroom",
        logo="images/logos/CoL.png",
        url="https://london.ca/newsroom",
        kind="page",
        homepage="https://london.ca/newsroom",
        accent="#cb30e0",
        max_items=20,
    ),
    Source(
        name="London Police Service",
        logo="images/logos/lps.svg",
        url="https://www.londonpolice.ca/news/authors/london-police-service",
        kind="page",
        homepage="https://www.londonpolice.ca/news/authors/london-police-service",
        accent="#0088ff",
        max_items=25,
    ),
    Source(
        name="104.7 Heart FM",
        logo="images/logos/heartfm.png",
        url="https://www.heartfm.ca/news/local-news/feed.xml",
        homepage="https://www.heartfm.ca/news/local-news/",
        accent="#ff2d55",
        max_items=30,
    ),

    # Direct institutional and public-service sources. These catch important local
    # information before it is necessarily rewritten by a newsroom.
    Source(
        name="Middlesex-London Health Unit",
        url="https://www.healthunit.com/news/",
        kind="page",
        homepage="https://www.healthunit.com/news/",
        accent="#007a78",
        max_items=12,
    ),
    Source(
        name="London Health Sciences Centre",
        url="https://www.lhsc.on.ca/news?page=0",
        kind="page",
        homepage="https://www.lhsc.on.ca/news",
        accent="#005596",
        max_items=12,
    ),
    Source(
        name="St. Joseph's Health Care London",
        url="https://www.sjhc.london.on.ca/news-and-media/news",
        kind="page",
        homepage="https://www.sjhc.london.on.ca/news-and-media/news",
        accent="#006b54",
        max_items=10,
    ),
    Source(
        name="Western News",
        url="https://news.westernu.ca/allnews/",
        kind="page",
        homepage="https://news.westernu.ca/",
        accent="#4f2683",
        max_items=12,
    ),
    Source(
        name="Fanshawe College Newsroom",
        url="https://www.fanshawec.ca/about-fanshawe/news",
        kind="page",
        homepage="https://www.fanshawec.ca/about-fanshawe/news",
        accent="#d71920",
        max_items=10,
    ),
    Source(
        name="Thames Valley District School Board",
        url="https://www.tvdsb.ca/news/",
        kind="page",
        homepage="https://www.tvdsb.ca/news/",
        accent="#006fba",
        max_items=12,
    ),
    Source(
        name="London District Catholic School Board",
        url="https://www.ldcsb.ca/apps/news/category/11195?pageIndex=1",
        kind="page",
        homepage="https://www.ldcsb.ca/apps/news/category/11195",
        accent="#2b5797",
        max_items=12,
    ),
    Source(
        name="London Transit Commission",
        url="https://www.londontransit.ca/",
        kind="page",
        homepage="https://www.londontransit.ca/",
        accent="#00694a",
        max_items=12,
    ),
    Source(
        name="Middlesex County",
        url="https://www.middlesex.ca/news",
        kind="page",
        homepage="https://www.middlesex.ca/news",
        accent="#315f43",
        max_items=12,
    ),
    Source(
        name="Environment Canada London Alerts",
        url="https://weather.gc.ca/rss/battleboard/onrm117_e.xml",
        homepage="https://weather.gc.ca/",
        accent="#2459a9",
        max_items=10,
    ),

    # National Canadian coverage. Keep each source deliberately bounded so a
    # national refresh does not overwhelm the London-first feed or action.
    Source(
        name="CBC News Canada",
        logo="images/logos/CBC_News_Logo.svg",
        # CBC's general Canada RSS endpoint intermittently times out behind its
        # CDN. The first-party Canada landing page is substantially more reliable
        # and still lets Scoop resolve and scrape the canonical CBC articles.
        url="https://www.cbc.ca/news/canada",
        kind="page",
        homepage="https://www.cbc.ca/news/canada",
        accent="#ff383c",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="Global News Canada",
        logo="images/logos/Global_News.svg",
        url="https://globalnews.ca/canada/feed/",
        homepage="https://globalnews.ca/canada/",
        accent="#0088ff",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="CTV News Canada",
        logo="images/logos/CTVNews_horizontal_logo.svg",
        url="https://www.ctvnews.ca/canada/",
        kind="page",
        homepage="https://www.ctvnews.ca/canada/",
        accent="#6155f5",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="The Globe and Mail",
        url="https://www.theglobeandmail.com/canada/",
        kind="page",
        homepage="https://www.theglobeandmail.com/",
        accent="#d71920",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="National Post",
        url="https://nationalpost.com/category/news/canada/",
        kind="page",
        homepage="https://nationalpost.com/",
        accent="#111111",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="Toronto Star",
        url="https://www.thestar.com/news/canada/",
        kind="page",
        homepage="https://www.thestar.com/",
        accent="#0072bc",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="CityNews Canada",
        url="https://toronto.citynews.ca/category/canada/",
        kind="page",
        homepage="https://www.citynews.ca/",
        accent="#e31837",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="Ontario Newsroom",
        url="https://news.ontario.ca/releases/en",
        kind="page",
        homepage="https://news.ontario.ca/en",
        accent="#1f5f38",
        max_items=15,
        scope="canada",
    ),
    Source(
        name="Government of Canada News",
        url="https://www.canada.ca/en/news.html?lang=en",
        kind="page",
        homepage="https://www.canada.ca/en/news.html",
        accent="#26374a",
        max_items=15,
        scope="canada",
    ),

    # Broad London discovery remains a safety net for smaller outlets and one-off
    # sources that are not practical to maintain as permanent direct collectors.
    Source(
        name="Google News London Discovery",
        logo="images/logos/google.png",
        url="https://news.google.com/rss/topics/CAAqHAgKIhZDQklTQ2pvSWJHOWpZV3hmZGpJb0FBUAE/sections/CAQiTkNCSVNORG9JYkc5allXeGZkakpDRUd4dlkyRnNYM1l5WDNObFkzUnBiMjV5Q2hJSUwyMHZNR0l4ZERGNkNnb0lMMjB2TUdJeGRERW9BQSowCAAqLAgKIiZDQklTRmpvSWJHOWpZV3hmZGpKNkNnb0lMMjB2TUdJeGRERW9BQVABUAE?hl=en-CA&gl=CA&ceid=CA:en",
        kind="google_topic",
        homepage="https://news.google.com/",
        accent="#0088ff",
        max_items=60,
    ),
]
