# SPAM website

A static site for the SPAM collaboration. No build step, no framework — GitHub
Pages serves the files exactly as they sit in the repo.

```
index.html                          the whole site, five tabs
assets/style.css
assets/app.js                       tabs, JSON loading, filter coverage plot
data/team.json                      edit to change the Team tab
data/catalogs.json                  edit to change the Catalogs tab
data/papers.json                    edit to change the Papers tab
data/arxiv.json                     written by the workflow, do not hand-edit
scripts/update_arxiv.py             the arXiv collector
.github/workflows/update-arxiv.yml  runs the collector weekly
.nojekyll                           tells Pages to skip Jekyll processing
```

## Turning the site on

1. Copy everything here into the root of the SPAM repo and push to `main`.
2. Repo → **Settings** → **Pages** → Source: **Deploy from a branch**,
   branch `main`, folder `/ (root)`. Save.
3. Wait a minute, then open `https://kelceydavis33.github.io/SPAM/`.

## Editing content

Everything on the site except the abstract comes from the three JSON files in
`data/`. You can edit them straight in the GitHub web editor — click the file,
click the pencil, commit. The site picks up the change on the next deploy,
usually under a minute.

`team.json` is a list of groups, each with a list of members. Add, remove or
reorder groups freely; the headings come from the `group` field.

`catalogs.json` is a list of releases. Leave `download`, `doi` or `readme`
as `""` and that button just won't render.

**Where to actually put the catalog files.** Not in this repo. GitHub caps
individual files at 100 MB and asks you to stay under 1 GB per repo, and Pages
bandwidth is not meant for bulk data. Put releases on
[Zenodo](https://zenodo.org) — free, no size problem in practice, and each
version gets its own DOI so papers can cite the exact catalog they used. Then
point `download` and `doi` at the Zenodo record. MAST is the other obvious home
once the data are archived there.

## The arXiv tab

`scripts/update_arxiv.py` queries the arXiv API, dedupes the results, and writes
`data/arxiv.json`. The workflow runs it at 06:00 UTC every Monday and commits
the file if anything changed. You can also trigger it by hand from the
**Actions** tab → *Update arXiv feed* → *Run workflow*.

Two things worth knowing before you trust the list:

**It searches metadata, not full text.** The arXiv API only indexes titles,
abstracts, author lists and comments. A paper that uses SPAM photometry but only
says so in its data section will never appear. If you want real full-text
coverage, the NASA ADS API supports `full:"SPAM"` queries — get a token at
<https://ui.adsabs.harvard.edu/user/settings/token>, store it as a repo secret,
and add an ADS query alongside the arXiv ones.

**"SPAM" is a terrible search term.** It collides with the e-mail literature, so
every query in the script pairs it with `JWST`, `CEERS` or `medium-band` and
restricts to `astro-ph.GA`. This will still let some junk through. When it does,
add the arXiv ID to the `IGNORE` list at the top of the script.

Also worth doing once the survey has a survey paper: ask people to cite it, and
watch its ADS citation list. That is the only reliable way to find everyone
using the data.

## Working on it locally

`fetch()` refuses to read JSON over `file://`, so opening `index.html` by
double-clicking will show "Could not load…" on every tab. Serve it instead:

```
python -m http.server 8000
```

then open <http://localhost:8000>.

## The coverage plot

The filter bandpasses are hardcoded near the top of `assets/app.js` as pivot
wavelength and width in microns. They are nominal NIRCam values — good enough
for a figure, but swap in the exact numbers from the JDox filter tables if you
want the plot to be quotable.
