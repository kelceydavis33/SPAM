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
import unicodedata
import urllib.request

DOC_ID = "1hIuAKhXKbIYI1VxKhqHcCJMBsa_sHM6EIk-KvbJOahs"
EXPORT_URL = "https://docs.google.com/document/d/" + DOC_ID + "/export?format=txt"

# Who goes in which section. Matching is case-insensitive and substring-based,
# so a first name is enough -- unless two team members share one, in which case
# use the full name here.
PIS = [
    ("Kelcey", "PI"),
    ("Rebecca", "Co-PI"),
]
ARCHITECTS = [
    ("Hollis", ""),
    ("Steve", ""),
]

# Emails and ORCIDs are parsed out of the doc but deliberately not published:
# the page shows names and affiliations only, as an author block would.


# LaTeX accent commands mapped to Unicode combining marks. Applying the mark
# after the base letter and normalising with NFC gets the composed character.
ACCENTS = {
    "'": "\u0301",  # acute
    "`": "\u0300",  # grave
    '"': "\u0308",  # diaeresis
    "^": "\u0302",  # circumflex
    "~": "\u0303",  # tilde
    "=": "\u0304",  # macron
    ".": "\u0307",  # dot above
    "u": "\u0306",  # breve
    "v": "\u030C",  # caron
    "H": "\u030B",  # double acute
    "c": "\u0327",  # cedilla
    "k": "\u0328",  # ogonek
    "d": "\u0323",  # dot below
    "b": "\u0331",  # macron below
    "r": "\u030A",  # ring above
}

# Standalone letter commands that are not accents over a base letter.
LIGATURES = {
    "ss": "\u00DF", "ae": "\u00E6", "AE": "\u00C6", "oe": "\u0153",
    "OE": "\u0152", "aa": "\u00E5", "AA": "\u00C5", "o": "\u00F8",
    "O": "\u00D8", "l": "\u0142", "L": "\u0141", "i": "i", "j": "j",
}

ACCENT_PATTERN = re.compile(
    r"\\([`'\"^~=.uvHckdbr])\s*(?:\{\s*(?:\\([ij])\b|([A-Za-z]))\s*\}|\\([ij])\b|([A-Za-z]))"
)
BRACED_NAME = re.compile(r"^\{(?P<given>[^{}]*)\}\s*\{(?P<family>[^{}]*)\}$")

LIGATURE_PATTERN = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|[oOlLij])(?![A-Za-z])[ ]?")


def delatex(value):
    """Turn LaTeX source into readable text.

    The doc holds real AASTeX, so names and affiliations arrive with escapes
    like \\'e, \\&, ~ and brace groups. Rendering those raw would put
    backslashes on the page.
    """
    if not value:
        return ""

    def accent(match):
        mark = ACCENTS[match.group(1)]
        base = match.group(2) or match.group(3) or match.group(4) or match.group(5) or ""
        return unicodedata.normalize("NFC", base + mark)

    value = ACCENT_PATTERN.sub(accent, value)
    value = LIGATURE_PATTERN.sub(lambda m: LIGATURES[m.group(1)], value)

    # Escaped punctuation.
    for escaped, plain in (("\\&", "&"), ("\\%", "%"), ("\\$", "$"),
                           ("\\#", "#"), ("\\_", "_"), ("\\{", "{"), ("\\}", "}")):
        value = value.replace(escaped, plain)

    # Spacing commands and non-breaking spaces.
    value = re.sub(r"\\[,;:!]", " ", value)
    value = value.replace("\\ ", " ").replace("~", " ")

    # Anything left that looks like a command, then stray braces.
    value = re.sub(r"\\[A-Za-z]+[ ]?", "", value)
    value = value.replace("{", "").replace("}", "")

    return " ".join(value.split())


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
        raw_name, _ = read_braced(block, brace)
        raw_name = " ".join(raw_name.split())
        if not raw_name:
            continue

        # AASTeX lets authors group their surname: \author{{Given} {Family}}.
        # Read it before delatex strips the braces, so sorting stays correct.
        grouped = BRACED_NAME.match(raw_name)
        sort_name = delatex(grouped.group("family")) if grouped else ""

        name = delatex(raw_name)
        if not name:
            continue

        record = {
            "name": name,
            "sort_name": sort_name,
            "orcid": orcid,
            "affiliations": [delatex(a) for a in find_field(block, "affiliation")],
            "altaffiliation": [delatex(a) for a in find_field(block, "altaffiliation")],
            "emails": find_field(block, "email"),
        }

        if is_template(record):
            print("  skipping template block:", name)
            continue

        authors.append(record)

    return authors


def surname(author):
    """Surname for sorting: the author's own grouping if given, else a guess."""
    if author.get("sort_name"):
        return author["sort_name"].lower()

    parts = author["name"].replace(",", " ").split()
    if not parts:
        return ""
    # Skip a trailing suffix so "Jane Doe Jr." sorts under Doe.
    while len(parts) > 1 and parts[-1].rstrip(".").lower() in ("jr", "sr", "ii", "iii", "iv"):
        parts.pop()

    # Strip accents for sorting so Ö files with O rather than after Z.
    stripped = unicodedata.normalize("NFD", parts[-1].lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def in_config_order(authors, entries):
    """Pick out named people, ordered as listed above rather than as the doc
    happens to list them, since PI order is meaningful.

    Returns (author, role) pairs.
    """
    picked = []
    for pattern, role in entries:
        for author in authors:
            already = any(author is chosen for chosen, _ in picked)
            if pattern.lower() in author["name"].lower() and not already:
                picked.append((author, role))
                break
        else:
            print("  warning: no author matched", repr(pattern))
    return picked


def to_member(author, role):
    """One person as the site renders them: name, role, affiliations inline."""
    member = {"name": author["name"]}
    if role:
        member["role"] = role
    if author["affiliations"]:
        member["affiliations"] = author["affiliations"]
    if author["altaffiliation"]:
        member["notes"] = author["altaffiliation"]
    return member


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

    pis = in_config_order(authors, PIS)
    taken = [author for author, _ in pis]
    architects = [
        (author, role)
        for author, role in in_config_order(authors, ARCHITECTS)
        if author not in taken
    ]
    taken += [author for author, _ in architects]

    others = sorted(
        (a for a in authors if a not in taken),
        key=lambda a: (surname(a), a["name"]),
    )

    groups = []
    if pis:
        groups.append({
            "group": "Principal investigators",
            "members": [to_member(a, role) for a, role in pis],
        })
    if architects:
        groups.append({
            "group": "Architects",
            "members": [to_member(a, role) for a, role in architects],
        })
    if others:
        groups.append({
            "group": "Team",
            "members": [to_member(a, "") for a in others],
        })

    total = sum(len(g["members"]) for g in groups)

    missing = [a["name"] for a in authors if not a["affiliations"]]
    if missing:
        print("  warning: no \\affiliation found for:", ", ".join(missing))

    # Flag affiliations that look like the same place typed two ways.
    prefixes = {}
    for author in authors:
        for affiliation in author["affiliations"]:
            prefixes.setdefault(affiliation[:28].lower(), set()).add(affiliation)
    for variants in prefixes.values():
        if len(variants) > 1:
            print("  note: these start alike, merge in the doc if the same place:")
            for variant in sorted(variants):
                print("        -", variant[:90])

    with open("data/team.json", "w") as handle:
        json.dump({"groups": groups}, handle, indent=2, ensure_ascii=False)

    print("Wrote", total, "people to data/team.json")
    for group in groups:
        print(" ", group["group"] + ":", ", ".join(m["name"] for m in group["members"]))


if __name__ == "__main__":
    main()
