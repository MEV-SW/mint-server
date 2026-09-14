"""RSS feed list for the issue-clustering experiment.

Derived from app/services/seed.py (RSS sources only). Notice/news pages that
need HTML scraping are omitted here to keep the corpus builder self-contained.
"""

FEEDS: list[dict[str, str]] = [
    # --- Korean industry / auto press ---
    {"name": "모터그래프", "url": "https://www.motorgraph.com/rss/allArticle.xml", "lang": "ko"},
    {"name": "오토헤럴드", "url": "https://www.autoherald.co.kr/rss/allArticle.xml", "lang": "ko"},
    {"name": "전자신문", "url": "https://rss.etnews.com/Section901.xml", "lang": "ko"},
    {"name": "ZDNet Korea", "url": "https://feeds.feedburner.com/zdkorea", "lang": "ko"},
    {"name": "연합뉴스 산업", "url": "https://www.yna.co.kr/rss/industry.xml", "lang": "ko"},
    # --- Korean policy ---
    {"name": "정책브리핑 정책뉴스", "url": "https://www.korea.kr/rss/policy.xml", "lang": "ko"},
    {"name": "정책브리핑 부처 브리핑", "url": "https://www.korea.kr/rss/ebriefing.xml", "lang": "ko"},
    {"name": "기후에너지환경부 공지·공고", "url": "https://www.mcee.go.kr/home/web/board/rss.do?menuId=290&boardMasterId=39", "lang": "ko"},
    {"name": "기후에너지환경부 보도·해명자료", "url": "https://www.mcee.go.kr/home/web/board/rss.do?menuId=286&boardMasterId=1", "lang": "ko"},
    {"name": "기후에너지환경부 환경정책", "url": "https://www.mcee.go.kr/home/web/policy_data/rss.do?menuId=92", "lang": "ko"},
    {"name": "기후에너지환경부 고시·훈령·예규", "url": "https://www.mcee.go.kr/home/web/law/rss.do?menuId=71&condition.typeCode=admrul", "lang": "ko"},
    # --- Autonomous driving (EN) ---
    {"name": "Autonomous Vehicle International", "url": "https://www.autonomousvehicleinternational.com/feed", "lang": "en"},
    {"name": "Automotive News", "url": "https://www.autonews.com/arc/outboundfeeds/rss/?outputType=xml", "lang": "en"},
    {"name": "Electrek Autonomous", "url": "https://electrek.co/guides/autonomous/feed/", "lang": "en"},
]
