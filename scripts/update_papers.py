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

# Queries are grouped by what they catch. A paper can match several groups and
# carries every tag it matched, so the page can filter on them.
#
# Two name collisions shape these. "SPAM" hits the e-mail filtering literature,
# so it is always paired with a term only this field uses. "MINERVA" is also the
# Miniature Exoplanet Radial Velocity Array, so it is never searched alone.
ARXIV_QUERIES = {
    "SPAM": [
        'cat:astro-ph.GA AND abs:"SPAM" AND abs:"JWST"',
        'cat:astro-ph.GA AND abs:"SPAM" AND abs:"CEERS"',
        'cat:astro-ph.GA AND abs:"SPAM" AND abs:"medium-band"',
        'abs:"Star-formation from Photometry through the Addition of Medium-bands"',
        'abs:"GO 8559" OR abs:"Program 8559"',
    ],
    # Both words, not either. Precise enough to need no other guard, and it is
    # what finds the MINERVA survey paper, whose abstract names CEERS.
    "MINERVA": [
        'cat:astro-ph.GA AND abs:"MINERVA" AND abs:"CEERS"',
        'abs:"Medium-band Imaging with NIRCam to Explore ReVolutionary Astrophysics"',
        'abs:"GO 7814" OR abs:"Program 7814"',
    ],
}

# Papers that never name a program in the abstract are reached through ADS full
# text instead -- see ADS_QUERIES below. An abstract-level net wide enough to
# catch them would return most medium-band imaging work regardless of field.

RESULTS_PER_QUERY = 60

# full: covers title, abstract, body and acknowledgements. database:astronomy
# keeps the physics and general-science corpus out.
#
# Full text is the only way to reach papers that use the data but name no
# program in the abstract, since the program ID nearly always appears in the
# data section. Deliberately not searching full text for "CEERS" alone, which
# would return a large slice of the extragalactic literature.
ADS_QUERIES = [
    'full:"SPAM" AND full:"CEERS" AND database:astronomy',
    'full:"SPAM" AND full:"NIRCam" AND database:astronomy',
    'full:"Star-formation from Photometry through the Addition of Medium-bands"',
    '(full:"GO 8559" OR full:"Program 8559" OR full:"JWST-GO-8559") AND database:astronomy',
    '(full:"GO 7814" OR full:"Program 7814" OR full:"JWST-GO-7814") AND database:astronomy',
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


def add(found, paper, tag):
    """Record a paper, merging tags when several queries turn up the same one."""
    if paper["id"] in IGNORE:
        return
    existing = found.get(paper["id"])
    if existing:
        if tag not in existing["tags"]:
            existing["tags"].append(tag)
        # An arXiv hit means the abstract names it, which beats a full-text hit.
        if existing["source"] == "ads" and paper["source"] == "arxiv":
            paper["tags"] = existing["tags"]
            found[paper["id"]] = paper
    else:
        paper["tags"] = [tag]
        found[paper["id"]] = paper


def main():
    found = {}

    for tag, queries in ARXIV_QUERIES.items():
        for query in queries:
            print("arXiv [" + tag + "]:", query)
            try:
                papers = arxiv_parse(arxiv_fetch(query, RESULTS_PER_QUERY))
            except Exception as error:
                print("  failed:", error)
                continue

            print("  got", len(papers))
            for paper in papers:
                add(found, paper, tag)

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
                add(found, paper, "Full text")

            time.sleep(1)

    papers = list(found.values())
    papers.sort(key=lambda paper: paper["published"], reverse=True)

    counts = {}
    for paper in papers:
        for tag in paper["tags"]:
            counts[tag] = counts.get(tag, 0) + 1

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "full_text_search": bool(token),
        "tags": list(ARXIV_QUERIES.keys()) + (["Full text"] if token else []),
        "papers": papers,
    }

    with open("data/arxiv.json", "w") as handle:
        json.dump(output, handle, indent=2)

    print("Wrote", len(papers), "papers to data/arxiv.json")
    for tag, count in sorted(counts.items()):
        print("  " + tag + ":", count)


if __name__ == "__main__":
    main()
