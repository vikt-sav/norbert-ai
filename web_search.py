"""
Гибридный веб-поиск:
- DuckDuckGo (общий веб)
- Crossref (научные статьи)
"""

import requests
import time
import re
from typing import List, Dict, Union
from ddgs import DDGS

from config import ENABLE_WEB_SEARCH, OPENALEX_EMAIL


# -----------------------------
# Translation (soft)
# -----------------------------
TRANSLATION_MAP = {
    "добыча": "mining",
    "свинец": "lead",
    "медь": "copper",
    "никель": "nickel",
    "золото": "gold",
    "серебро": "silver",
    "обогащение": "beneficiation",
    "флотация": "flotation",
    "выщелачивание": "leaching",
    "электроэкстракция": "electrowinning",
    "методы": "methods",
    "технологии": "technologies",
    "передовые": "advanced",
}


def translate_query(query: str) -> str:
    q = query.lower()
    for ru, en in TRANSLATION_MAP.items():
        q = q.replace(ru, en)

    q = re.sub(r"[^\w\s\-]", " ", q)
    q = re.sub(r"\s+", " ", q)

    return q.strip()


def safe_get(obj: Union[dict, str, None], key: str, default=""):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


# -----------------------------
# DDG SEARCH
# -----------------------------
def search_ddg(query: str, num_results: int = 5) -> List[Dict]:
    results = []

    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):

                if not isinstance(r, dict):
                    continue

                results.append({
                    "title": safe_get(r, "title"),
                    "snippet": safe_get(r, "body"),
                    "url": safe_get(r, "href"),
                    "source": "DuckDuckGo"
                })

    except Exception as e:
        print(f"⚠️ DDG error: {e}")

    return results


# -----------------------------
# CROSSREF SEARCH
# -----------------------------
def search_crossref(query: str, num_results: int = 5, retries: int = 2) -> List[Dict]:
    results = []

    q = translate_query(query) or "mining"

    print(f"   → Crossref query: '{q}'")

    url = "https://api.crossref.org/works"
    params = {
        "query": q,
        "rows": num_results,
        "sort": "relevance",
    }

    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL

    headers = {
        "User-Agent": f"HybridSearch/1.0 (mailto:{OPENALEX_EMAIL or 'anonymous'})"
    }

    for _ in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()

            items = data.get("message", {}).get("items", [])

            for item in items:
                title = (item.get("title") or [""])[0]

                abstract = item.get("abstract") or title

                authors = item.get("author", [])
                author_str = ", ".join(
                    f"{a.get('given','')} {a.get('family','')}".strip()
                    for a in authors[:5]
                    if isinstance(a, dict)
                ) or "Unknown"

                doi = item.get("DOI", "")
                link = f"https://doi.org/{doi}" if doi else ""

                year = ""
                try:
                    year = str(item.get("issued", {}).get("date-parts", [[None]])[0][0])
                except:
                    pass

                results.append({
                    "title": title,
                    "snippet": abstract[:400],
                    "url": link,
                    "authors": author_str,
                    "source": "Crossref",
                    "year": year
                })

            return results

        except Exception as e:
            print(f"⚠️ Crossref error: {e}")
            time.sleep(1)

    return []


# -----------------------------
# ROUTING
# -----------------------------
def is_academic(query: str) -> bool:
    q = query.lower()
    return any(x in q for x in ["paper", "doi", "journal", "study", "research", "article"])


# -----------------------------
# MAIN SEARCH
# -----------------------------
def web_search(query: str, num_results: int = 5) -> Dict[str, List[Dict]]:
    print(f"🔥 web_search: {query}")

    if not ENABLE_WEB_SEARCH:
        return {"web": [], "academic": []}

    if is_academic(query):
        web = []
        academic = search_crossref(query, num_results)
    else:
        web = search_ddg(query, num_results)
        academic = search_crossref(query, num_results)

    print(f"🔍 web results: {len(web)}")
    print(f"🔍 academic results: {len(academic)}")

    return {
        "web": web,
        "academic": academic
    }