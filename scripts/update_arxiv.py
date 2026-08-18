"""
Collect arXiv preprints that look like they use SPAM data and write data/arxiv.json.

Run by .github/workflows/update-arxiv.yml once a week. Only the standard
library is used, so there is nothing to install.

Note on scope: the arXiv API searches metadata (title, abstract, comments,
authors), not full text. A paper that only cites SPAM in its data section
will not show up here. See the README for the NASA ADS alternative.
"""

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

# "SPAM" on its own is hopeless -- it collides with e-mail spam papers. Each
# query pairs the survey name with something only this field would mention.
QUERIES = [
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"JWST"',
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"CEERS"',
    'cat:astro-ph.GA AND abs:"SPAM" AND abs:"medium-band"',
    'abs:"Star-formation from Photometry through the Addition of Medium-bands"',
    'abs:"GO 8559" OR abs:"Program 8559"',
]

# arXiv IDs to keep out of the list, for false positives that slip through.
IGNORE = [
    # "2401.01234",
]


def fetch(query, max_results=50):
    """Run one arXiv query and return the raw Atom XML."""
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "SPAM-site/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def parse(xml_bytes):
    """Pull the fields we display out of one Atom response."""
    root = ET.fromstring(xml_bytes)
    papers = []

    for entry in root.findall(ATOM + "entry"):
        full_id = entry.find(ATOM + "id").text
        # The id looks like http://arxiv.org/abs/2401.01234v2
        arxiv_id = full_id.split("/abs/")[-1].split("v")[0]

        names = []
        for author in entry.findall(ATOM + "author"):
            names.append(author.find(ATOM + "name").text)

        if len(names) > 4:
            author_line = ", ".join(names[:4]) + ", et al."
        else:
            author_line = ", ".join(names)

        papers.append({
            "id": arxiv_id,
            "title": " ".join(entry.find(ATOM + "title").text.split()),
            "authors": author_line,
            "published": entry.find(ATOM + "published").text,
            "url": "https://arxiv.org/abs/" + arxiv_id,
        })

    return papers


def main():
    found = {}

    for query in QUERIES:
        print("Querying:", query)
        try:
            xml_bytes = fetch(query)
        except Exception as error:
            print("  failed:", error)
            continue

        papers = parse(xml_bytes)
        print("  got", len(papers), "results")

        for paper in papers:
            if paper["id"] not in IGNORE:
                found[paper["id"]] = paper

        # arXiv asks for a few seconds between requests.
        time.sleep(3)

    papers = list(found.values())
    papers.sort(key=lambda paper: paper["published"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_note": "arXiv metadata search; see scripts/update_arxiv.py for the queries",
        "papers": papers,
    }

    with open("data/arxiv.json", "w") as handle:
        json.dump(output, handle, indent=2)

    print("Wrote", len(papers), "papers to data/arxiv.json")


if __name__ == "__main__":
    main()
