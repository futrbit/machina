from pathlib import Path

# RSS / site feeds grouped by category
FEEDS = {
    "autonomous": [
        "https://www.nvidia.com/en-us/rss/",
        "https://www.autonomousvehicleinternational.com/feed/",
        "https://spectrum.ieee.org/autonomous-vehicles/rss",
        "https://insideevs.com/rss/news/",
        "https://bair.berkeley.edu/blog/feed.xml",
        "https://medium.com/feed/self-driving-cars",
        "https://www.driverless.global/driverless-blog?format=feed&type=rss",
        "https://torc.ai/knowledge-center/articles/feed/",
        "https://www.theguardian.com/technology/self-driving-cars/rss",
        "https://research.google/blog/rss",
        "https://unite.ai/feed"
    ],
    "drones": [
        "https://dronedj.com/feed/",
        "https://www.suasnews.com/feed/",
        "https://www.droneblog.com/feed/",
        "https://www.unmannedsystemstechnology.com/feed/",
        "https://www.thedronegirl.com/feed/",
    ],
    "tech": [  # NEW category replaces "space"
        "https://rss.app/feed/9dVAfExLZVI8dH7C",
        "https://rss.app/feed/6Kh1TxCRVAQppVF1",
        "https://rss.app/feeds/6Kh1TxCRVAQppVF1.xml",
        "https://rss.app/feeds/zSQ0Cq2iBcfdvCZj.xml",
        "https://rss.app/feeds/ydNbdled86X5GKB4.xml",
        "https://rss.app/feeds/OLXsy5aoRRZ9ftVt.xml",
        "https://rss.app/feeds/7b9yfqEG7dAfwf9Q.xml",
        "https://rss.app/feeds/3RocfoyEX48CqgPR.xml",
        "https://rss.app/feeds/LMPUriH97J5plIHC.xml",
        "https://rss.app/feeds/7vnLwJFnDX8xOEDH.xml",
        "https://rss.app/feeds/xGvFNm82ukhOT1O7.xml",
        "https://rss.app/feeds/sPcYW9Zfoj1HHCdp.xml",
    ],
}

MODEL = "gpt-4o-mini"

# Paths for raw and rewritten data
DATA_DIR = Path(__file__).parent / "data" / "raw"
REWRITTEN_DIR = Path(__file__).parent / "data" / "rewritten"
