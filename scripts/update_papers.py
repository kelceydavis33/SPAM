"""
Find papers that use SPAM data and write data/arxiv.json.

Two sources:

  arXiv  -- metadata only (title, abstract, comments). Always runs.
  ADS    -- full text of the paper body. Only runs if ADS_TOKEN is set.

The ADS half is what catches a paper that credits the program in its data
section without ever saying SPAM in the abstract. Without a token the script
still works, it just sees less.

Run by .github/workflows/update-arxiv.yml. Standard library only.
"""

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ARXIV_API = "http://export.arxiv.org/api/query"
ADS_API = "https://api.adsabs.harvard.edu/v1/search/query"
ATOM = "{http://www.w3.org/2005/Atom}"

# "SPAM" alone is hopeless -- it collides with the e-mail filtering literature.
# Every query pairs it with something only this field would say.
ARXIV_QUERIES = [
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"JWST"',
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"CEERS"',
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"medium-band"',
    'abs:"Star-formation from Photometry through the Addition of Medium-bands"',
    'abs:"GO 8559" OR abs:"Program 8559"',
]

# full: covers title, abstract, body and acknowledgements. database:astronomy
# keeps the physics and general-science corpus out.
ADS_QUERIES = [
    'full:"SPAM" AND full:"CEERS" AND database:astronomy',
    'full:"SPAM" AND full:"NIRCam" AND database:astronomy',
    'full:"Star-formation from Photometry through the Addition of Medium-bands"',
    '(full:"GO 8559" OR full:"Program 8559" OR full:"JWST-GO-8559") AND database:astronomy',
]

# IDs to suppress -- arXiv numbers or ADS bibcodes -- for false positives.
IGNORE = [
    # "2401.01234",
]


def arxiv_fetch(query, max_results=50):
    """Run one arXiv query and return the raw Atom XML."""
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "SPAM-site/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def format_authors(names):
    """Trim a long author list down to something that fits on one line."""
    if len(names) > 4:
        return ", ".join(names[:4]) + ", et al."
    return ", ".join(names)


def arxiv_parse(xml_bytes):
    """Pull the fields we display out of one Atom response."""
    root = ET.fromstring(xml_bytes)
    papers = []

    for entry in root.findall(ATOM + "entry"):
        full_id = entry.find(ATOM + "id").text
        # The id looks like http://arxiv.org/abs/2401.01234v2
        arxiv_id = full_id.split("/abs/")[-1].split("v")[0]

        names = [author.find(ATOM + "name").text for author in entry.findall(ATOM + "author")]

        papers.append({
            "id": arxiv_id,
            "title": " ".join(entry.find(ATOM + "title").text.split()),
            "authors": format_authors(names),
            "published": entry.find(ATOM + "published").text,
            "url": "https://arxiv.org/abs/" + arxiv_id,
            "source": "arxiv",
        })

    return papers


def ads_fetch(query, token, rows=50):
    """Run one ADS query and return the decoded JSON."""
    params = {
        "q": query,
        "fl": "bibcode,title,author,pubdate,identifier",
        "rows": rows,
        "sort": "date desc",
    }
    url = ADS_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "User-Agent": "SPAM-site/1.0",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def ads_parse(payload):
    """Turn ADS documents into the same shape as the arXiv ones."""
    papers = []

    for doc in payload.get("response", {}).get("docs", []):
        # Prefer the arXiv ID so ADS and arXiv hits for the same paper collapse
        # into one entry rather than appearing twice.
        arxiv_id = ""
        for identifier in doc.get("identifier", []):
            if identifier.lower().startswith("arxiv:"):
                arxiv_id = identifier.split(":", 1)[1]
                break

        if arxiv_id:
            paper_id = arxiv_id
            url = "https://arxiv.org/abs/" + arxiv_id
        else:
            paper_id = doc["bibcode"]
            url = "https://ui.adsabs.harvard.edu/abs/" + doc["bibcode"]

        # ADS dates look like 2025-01-00 when the day is unknown.
        published = doc.get("pubdate", "").replace("-00", "-01")

        papers.append({
            "id": paper_id,
            "title": doc.get("title", ["Untitled"])[0],
            "authors": format_authors(doc.get("author", [])),
            "published": published,
            "url": url,
            "source": "ads",
        })

    return papers


def main():
    found = {}

    for query in ARXIV_QUERIES:
        print("arXiv:", query)
        try:
            papers = arxiv_parse(arxiv_fetch(query))
        except Exception as error:
            print("  failed:", error)
            continue

        print("  got", len(papers))
        for paper in papers:
            if paper["id"] not in IGNORE:
                found[paper["id"]] = paper

        # arXiv asks for a few seconds between requests.
        time.sleep(3)

    token = os.environ.get("ADS_TOKEN", "").strip()

    if not token:
        print("No ADS_TOKEN set, skipping full-text search.")
    else:
        for query in ADS_QUERIES:
            print("ADS:", query)
            try:
                papers = ads_parse(ads_fetch(query, token))
            except Exception as error:
                print("  failed:", error)
                continue

            print("  got", len(papers))
            for paper in papers:
                if paper["id"] in IGNORE:
                    continue
                # An arXiv hit already means the abstract mentions SPAM, which is
                # the stronger signal, so do not let ADS overwrite it.
                if paper["id"] not in found:
                    found[paper["id"]] = paper

            time.sleep(1)

    papers = list(found.values())
    papers.sort(key=lambda paper: paper["published"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "full_text_search": bool(token),
        "papers": papers,
    }

    with open("data/arxiv.json", "w") as handle:
        json.dump(output, handle, indent=2)

    print("Wrote", len(papers), "papers to data/arxiv.json")


if __name__ == "__main__":
    main()
