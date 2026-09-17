"""
Find papers that name SPAM or MINERVA and write data/arxiv.json.

Two sources:

  arXiv  -- title and abstract of preprints.
  ADS    -- title and abstract of the published record. Needs ADS_TOKEN.

Searches are only a way to gather candidates. What a paper is actually tagged
with is decided here, by looking for the program name in its own title and
abstract. A paper that merely cites a program, or names it in an
acknowledgement, does not qualify and is dropped.

Run by .github/workflows/update-arxiv.yml. Standard library only.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ARXIV_API = "https://export.arxiv.org/api/query"
ADS_API = "https://api.adsabs.harvard.edu/v1/search/query"
ATOM = "{http://www.w3.org/2005/Atom}"

# A paper must place itself in this field before an ambiguous name in it will
# be read as one of ours. Deliberately no bare "JWST" here: almost every
# exoplanet abstract mentions JWST somewhere, which let through papers using
# the MINERVA array and SPAM-like limb-darkening coefficients. Both programs
# are NIRCam medium-band surveys, so a paper actually using their data says
# NIRCam, CEERS or medium band.
CONTEXT = [
    r"\bCEERS\b",
    r"\bNIRCam\b",
    r"medium[\s-]?bands?\b",
]

# The tags a paper can carry, and how each one is recognised, against the
# title and abstract only.
#
#   certain   -- names nothing else in the literature shares. Enough on its own.
#   ambiguous -- the bare acronym. Only counts inside CONTEXT.
#   exclude   -- vetoes the tag outright, checked before either.
#
# A paper can earn both tags. Everything that earns none is discarded.
PROGRAMS = {
    "SPAM": {
        "certain": [
            r"Star[\s-]?formation from Photometry through the Addition of Medium[\s-]?bands",
            r"\b(?:GO|PID|Program|JWST-GO)[\s#-]*8559\b",
        ],
        "ambiguous": [
            r"\bSPAM\b",
        ],
        # Intema's Source Peeling and Atmospheric Modeling radio pipeline, and
        # the Synthetic Photometry Atmosphere Model limb-darkening coefficients.
        "exclude": [
            r"Source Peeling",
            r"SPAM pipeline",
            r"SPAM[\s-]?like",
            r"limb[\s-]?darkening",
        ],
    },
    "MINERVA": {
        "certain": [
            r"Medium[\s-]?band Imaging with NIRCam to Explore ReVolutionary Astrophysics",
            r"\b(?:GO|PID|Program|JWST-GO)[\s#-]*7814\b",
        ],
        "ambiguous": [
            r"\bMINERVA\b",
        ],
        # The Miniature Exoplanet Radial Velocity Array and its Australis arm,
        # and the Hayabusa2 MINERVA-II rovers.
        "exclude": [
            r"MINERVA[\s-]?Australis",
            r"Miniature Exoplanet Radial Velocity Array",
            r"MINERVA[\s-]?(?:II|2|I)\b",
        ],
    },
}

# Candidate searches. These only have to find the paper -- PROGRAMS decides
# whether it stays. Both fields are searched because a survey paper puts the
# name in its title and a science paper puts it in its abstract.
#
# Written out as an explicit category list rather than "cat:astro-ph", which
# matches only the legacy pre-2007 designation and would return nearly nothing.
ASTRO = ("(cat:astro-ph.GA OR cat:astro-ph.CO OR cat:astro-ph.EP OR "
         "cat:astro-ph.HE OR cat:astro-ph.IM OR cat:astro-ph.SR OR cat:astro-ph)")

ARXIV_QUERIES = [
    ASTRO + ' AND (abs:"SPAM" OR ti:"SPAM")',
    ASTRO + ' AND (abs:"MINERVA" OR ti:"MINERVA")',
    'abs:"Star-formation from Photometry through the Addition of Medium-bands"',
    'abs:"Medium-band Imaging with NIRCam to Explore ReVolutionary Astrophysics"',
]

# ADS reaches the published version and anything never posted to arXiv. Note
# these are abs: and title:, not full: -- searching the body is what dragged in
# every paper that merely cites one of these programs.
ADS_QUERIES = [
    '(abs:"SPAM" OR title:"SPAM") AND database:astronomy',
    '(abs:"MINERVA" OR title:"MINERVA") AND database:astronomy',
    'abs:"Star-formation from Photometry through the Addition of Medium-bands"',
    'abs:"Medium-band Imaging with NIRCam to Explore ReVolutionary Astrophysics"',
    '(abs:"GO 8559" OR abs:"Program 8559" OR abs:"GO 7814" OR abs:"Program 7814") AND database:astronomy',
]

# Results come back newest first, so a cap the match count outgrows silently
# drops the oldest papers off the end of the feed.
RESULTS_PER_QUERY = 200

# IDs to suppress -- arXiv numbers or ADS bibcodes -- for false positives.
IGNORE = [
    # "2401.01234",
]


def classify(paper):
    """Return the tags a paper earns from its own title and abstract.

    A title naming exactly one of the programs wins outright: the paper is
    about that program, and the other name appearing somewhere in the abstract
    is background rather than a second subject.
    """
    title = paper.get("title") or ""
    text = title + "\n" + (paper.get("abstract") or "")

    def hits(patterns, where):
        return any(re.search(p, where, re.IGNORECASE) for p in patterns)

    # Context is judged on the whole record. Plenty of legitimate titles name a
    # program without room for NIRCam or CEERS beside it.
    in_context = hits(CONTEXT, text)

    tags = []
    from_title = []

    for name, rules in PROGRAMS.items():
        if hits(rules["exclude"], text):
            continue
        if not (hits(rules["certain"], text)
                or (in_context and hits(rules["ambiguous"], text))):
            continue

        tags.append(name)

        if (hits(rules["certain"], title)
                or (in_context and hits(rules["ambiguous"], title))):
            from_title.append(name)

    if len(from_title) == 1:
        return from_title

    return tags


def arxiv_fetch(query, max_results=50, attempts=3):
    """Run one arXiv query and return the raw Atom XML.

    arXiv rejects or drops requests from cloud IPs often enough that a single
    attempt is not reliable from a CI runner, so each query is retried with a
    growing pause before it is allowed to count as a failure.
    """
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": "SPAM-site/1.0 (+https://github.com/kelceydavis33/SPAM)",
    })

    last_error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as error:
            last_error = error
            print("  attempt", attempt + 1, "failed:", error)
            if attempt + 1 < attempts:
                time.sleep(10 * (attempt + 1))

    raise last_error


def format_authors(names):
    """Trim a long author list down to something that fits on one line."""
    if len(names) > 4:
        return ", ".join(names[:4]) + ", et al."
    return ", ".join(names)


def text_of(element):
    """Collapse whitespace in an Atom text node, tolerating an empty one."""
    if element is None or element.text is None:
        return ""
    return " ".join(element.text.split())


def arxiv_parse(xml_bytes):
    """Pull the fields we need out of one Atom response."""
    root = ET.fromstring(xml_bytes)
    papers = []

    for entry in root.findall(ATOM + "entry"):
        full_id = entry.find(ATOM + "id").text
        # The id looks like http://arxiv.org/abs/2401.01234v2
        arxiv_id = full_id.split("/abs/")[-1].split("v")[0]

        names = [author.find(ATOM + "name").text for author in entry.findall(ATOM + "author")]

        papers.append({
            "id": arxiv_id,
            "title": text_of(entry.find(ATOM + "title")),
            "abstract": text_of(entry.find(ATOM + "summary")),
            "authors": format_authors(names),
            "published": entry.find(ATOM + "published").text,
            "url": "https://arxiv.org/abs/" + arxiv_id,
            "source": "arxiv",
        })

    return papers


def ads_fetch(query, token, rows=200):
    """Run one ADS query and return the decoded JSON."""
    params = {
        "q": query,
        "fl": "bibcode,title,abstract,author,pubdate,identifier",
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
            "abstract": doc.get("abstract", "") or "",
            "authors": format_authors(doc.get("author", [])),
            "published": published,
            "url": url,
            "source": "ads",
        })

    return papers


def add(found, paper):
    """Record a paper if it earns a tag, merging with any earlier sighting."""
    if paper["id"] in IGNORE:
        return False

    tags = classify(paper)
    if not tags:
        return False

    existing = found.get(paper["id"])
    if existing:
        for tag in tags:
            if tag not in existing["tags"]:
                existing["tags"].append(tag)
        # An arXiv record is the better copy: cleaner abstract, real timestamp.
        if existing["source"] == "ads" and paper["source"] == "arxiv":
            paper["tags"] = existing["tags"]
            found[paper["id"]] = paper
    else:
        paper["tags"] = tags
        found[paper["id"]] = paper

    return True


def load_previous():
    """Read the feed already on disk, so a bad run can decline to replace it."""
    try:
        with open("data/arxiv.json") as handle:
            return json.load(handle).get("papers", [])
    except (OSError, ValueError):
        return []


def main():
    found = {}
    attempted = 0
    failed = 0

    for query in ARXIV_QUERIES:
        print("arXiv:", query)
        attempted += 1
        try:
            papers = arxiv_parse(arxiv_fetch(query, RESULTS_PER_QUERY))
        except Exception as error:
            print("  gave up:", error)
            failed += 1
            continue

        kept = sum(1 for paper in papers if add(found, paper))
        print("  got", len(papers), "->", kept, "tagged")

        # arXiv asks for a few seconds between requests.
        time.sleep(3)

    token = os.environ.get("ADS_TOKEN", "").strip()

    if not token:
        print("No ADS_TOKEN set, skipping the published record.")
    else:
        for query in ADS_QUERIES:
            print("ADS:", query)
            attempted += 1
            try:
                papers = ads_parse(ads_fetch(query, token, RESULTS_PER_QUERY))
            except Exception as error:
                print("  failed:", error)
                failed += 1
                continue

            kept = sum(1 for paper in papers if add(found, paper))
            print("  got", len(papers), "->", kept, "tagged")

            time.sleep(1)

    papers = list(found.values())
    papers.sort(key=lambda paper: paper["published"], reverse=True)

    # The abstract is only needed for tagging. Keep it out of the published file.
    for paper in papers:
        paper.pop("abstract", None)

    if failed:
        print(failed, "of", attempted, "queries failed.")

    # A run that found nothing is only trustworthy if every query actually ran.
    # Otherwise the sensible move is to leave the last good feed in place, and
    # fail loudly so the Actions run goes red instead of quietly erasing it.
    previous = load_previous()

    if not papers and failed:
        raise SystemExit(
            "Queries failed and nothing was found. Keeping the "
            + str(len(previous))
            + " paper(s) already on file."
        )

    if not papers and previous:
        raise SystemExit(
            "Search came back empty but "
            + str(len(previous))
            + " paper(s) are on file. Not overwriting. "
            "Delete data/arxiv.json by hand if they really should go."
        )

    counts = {}
    for paper in papers:
        for tag in paper["tags"]:
            counts[tag] = counts.get(tag, 0) + 1

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Titles and abstracts only, whichever sources were available.
        "full_text_search": False,
        "tags": list(PROGRAMS.keys()),
        "papers": papers,
    }

    with open("data/arxiv.json", "w") as handle:
        json.dump(output, handle, indent=2)

    print("Wrote", len(papers), "papers to data/arxiv.json")
    for tag, count in sorted(counts.items()):
        print("  " + tag + ":", count)


if __name__ == "__main__":
    main()
