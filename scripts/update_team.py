"""
Build data/team.json from the SPAM Team Info Google Doc.

The doc collects AASTeX author blocks in this shape:

    \\author[0000-0000-0000-0000]{First Last Name}
    \\altaffiliation{If applicable}
    \\affiliation{Affiliation}
    \\email{name@email.com}

This reads the doc's plain-text export, pulls out those blocks, and sorts
people into PIs, architects, and everyone else alphabetically by surname.

The doc must be shared as "Anyone with the link -> Viewer" or the export
returns a login page instead of the text.

Run by .github/workflows/update-team.yml. Standard library only.
"""

import json
import re
import urllib.request

DOC_ID = "1hIuAKhXKbIYI1VxKhqHcCJMBsa_sHM6EIk-KvbJOahs"
EXPORT_URL = "https://docs.google.com/document/d/" + DOC_ID + "/export?format=txt"

# Who goes in which section. Matching is case-insensitive and substring-based,
# so a first name is enough -- unless two team members share one, in which case
# use the full name here.
PIS = ["Kelcey", "Rebecca"]
ARCHITECTS = ["Hollis", "Steve"]

# Emails and ORCIDs are parsed out of the doc but deliberately not published:
# the page shows names and affiliations only, as an author block would.


def read_braced(text, open_index):
    """Read a {...} group starting at open_index, respecting nested braces."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index], index + 1
    return "", len(text)


def find_field(block, command):
    """Pull the contents of every \\command{...} in one author block."""
    values = []
    for match in re.finditer(r"\\" + command + r"\s*\{", block):
        value, _ = read_braced(block, match.end() - 1)
        cleaned = " ".join(value.split())
        if cleaned:
            values.append(cleaned)
    return values


def is_template(author):
    """The doc's instructions contain a literal example block. Skip it."""
    placeholders = {"first last name", "first last", "name"}
    if author["name"].strip().lower() in placeholders:
        return True
    if "name@email.com" in " ".join(author["emails"]).lower():
        return True
    if [a.lower() for a in author["affiliations"]] == ["affiliation"]:
        return True
    return False


def parse_authors(text):
    """Turn the whole document into a list of author records."""
    # Normalise the curly quotes and non-breaking spaces Docs likes to insert.
    text = text.replace("\u00a0", " ").replace("\u201c", '"').replace("\u201d", '"')

    starts = [match.start() for match in re.finditer(r"\\author\b", text)]
    authors = []

    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(text)
        block = text[start:end]

        # ORCID sits in the optional [...] before the name.
        orcid = ""
        orcid_match = re.match(r"\\author\s*\[([^\]]*)\]", block)
        if orcid_match:
            candidate = orcid_match.group(1).strip()
            # Ignore the placeholder people forget to replace.
            if candidate and candidate != "0000-0000-0000-0000":
                orcid = candidate

        brace = block.find("{")
        if brace == -1:
            continue
        name, _ = read_braced(block, brace)
        name = " ".join(name.split())
        if not name:
            continue

        record = {
            "name": name,
            "orcid": orcid,
            "affiliations": find_field(block, "affiliation"),
            "altaffiliation": find_field(block, "altaffiliation"),
            "emails": find_field(block, "email"),
        }

        if is_template(record):
            print("  skipping template block:", name)
            continue

        authors.append(record)

    return authors


def surname(name):
    """Best-effort surname for sorting. Compound names may need a manual fix."""
    parts = name.replace(",", " ").split()
    if not parts:
        return ""
    # Skip a trailing suffix so "Jane Doe Jr." sorts under Doe.
    while len(parts) > 1 and parts[-1].rstrip(".").lower() in ("jr", "sr", "ii", "iii", "iv"):
        parts.pop()
    return parts[-1].lower()


def matches(author, patterns):
    lowered = author["name"].lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def build_author_block(ordered):
    """Number affiliations in order of first appearance, the way LaTeX does.

    Returns the shared affiliation and note lists plus, for each author, the
    marker indices pointing into them.
    """
    affiliations = []
    notes = []
    entries = []

    for author in ordered:
        affil_indices = []
        for affiliation in author["affiliations"]:
            if affiliation not in affiliations:
                affiliations.append(affiliation)
            affil_indices.append(affiliations.index(affiliation) + 1)

        note_indices = []
        for note in author["altaffiliation"]:
            if note not in notes:
                notes.append(note)
            note_indices.append(notes.index(note) + 1)

        entry = {"name": author["name"], "affils": affil_indices}
        if note_indices:
            entry["notes"] = note_indices
        entries.append(entry)

    return entries, affiliations, notes


def main():
    print("Fetching", EXPORT_URL)
    request = urllib.request.Request(EXPORT_URL, headers={"User-Agent": "SPAM-site/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8", errors="replace")

    if "accounts.google.com" in text or "<html" in text.lower():
        raise SystemExit(
            "The export returned a login page. Set the doc's sharing to "
            "'Anyone with the link -> Viewer' and run this again."
        )

    authors = parse_authors(text)
    print("Found", len(authors), "author blocks")

    if not authors:
        # Never overwrite a good team list with an empty one.
        raise SystemExit("No author blocks found; leaving data/team.json alone.")

    pis = [a for a in authors if matches(a, PIS)]
    architects = [a for a in authors if matches(a, ARCHITECTS) and a not in pis]
    named = pis + architects
    others = sorted(
        (a for a in authors if a not in named),
        key=lambda a: (surname(a["name"]), a["name"]),
    )

    # One pass over everyone in display order, so affiliation numbers run
    # top to bottom across the whole page as they would in a paper.
    ordered = pis + architects + others
    entries, affiliations, notes = build_author_block(ordered)

    by_name = {}
    for entry in entries:
        by_name[entry["name"]] = entry

    groups = []
    for label, people in (
        ("Principal investigators", pis),
        ("Architects", architects),
        ("Team", others),
    ):
        if people:
            groups.append({
                "group": label,
                "authors": [by_name[a["name"]] for a in people],
            })

    output = {
        "groups": groups,
        "affiliations": affiliations,
        "notes": notes,
    }

    with open("data/team.json", "w") as handle:
        json.dump(output, handle, indent=2)

    print("Wrote", len(ordered), "people and", len(affiliations), "affiliations")
    for group in groups:
        print(" ", group["group"] + ":", ", ".join(a["name"] for a in group["authors"]))


if __name__ == "__main__":
    main()
