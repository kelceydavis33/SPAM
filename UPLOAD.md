# Manual upload — step by step

No git, no SSH. Everything below happens in the browser.

## 1. Delete the flattened files already in the repo

Go to <https://github.com/kelceydavis33/SPAM>. These seven files are sitting in
the root where they don't belong. For each one: click the filename, click the
trash icon (top right of the file view), then **Commit changes**.

    app.js
    style.css
    update_arxiv.py
    team.json
    catalogs.json
    papers.json
    arxiv.json

Leave `index.html`, `README.md` and `LICENSE` alone — `index.html` gets
overwritten in the next step.

## 2. Unzip and upload the folders

Unzip `spam-site.zip`. You get a folder called `spam-site` containing
`index.html` plus three folders: `assets`, `data`, `scripts`.

In the repo, click **Add file** → **Upload files**. Then open the `spam-site`
folder on your computer, select the four visible items — `index.html`, `assets`,
`data`, `scripts` — and drag them onto the upload area together.

Dragging the *folders themselves* is what matters. GitHub reads the folder names
and rebuilds the structure. Dragging loose files that you opened out of the
folders is what flattened everything last time.

You should see a file list appear that reads `assets/app.js`, `data/team.json`
and so on, with the slashes. If the slashes are missing, the structure was lost
again — cancel and re-drag the folders rather than their contents.

Scroll down, click **Commit changes**.

## 3. Create the workflow file by hand

The `.github` folder starts with a dot, so your file manager hides it and the
uploader will not pick it up. This one has to be typed.

In the repo, click **Add file** → **Create new file**. In the filename box type
exactly:

    .github/workflows/update-arxiv.yml

The box will split into folder segments as you type each slash — that is what it
looks like when it is working.

Open `spam-site/.github/workflows/update-arxiv.yml` from the unzipped folder in
any text editor, copy the whole thing, and paste it into the editor on GitHub.
(If your file manager hides the folder, press Ctrl+H in Files to reveal it, or
open the file straight from the zip.)

Click **Commit changes**.

## 4. Run it

Go to the **Actions** tab. *Update arXiv feed* now appears in the left sidebar.
Click it, then **Run workflow** → branch `main` → **Run workflow**.

It takes about half a minute. When it finishes it will have written
`data/arxiv.json`. On a brand new survey it will likely find nothing, and the
arXiv tab will say so — that is correct behaviour, not a failure.

Note that the workflow will only show up in the *runs* list on the main Actions
page after it has run at least once. Before then, look in the left sidebar.

## 5. Check the site

Open <https://kelceydavis33.github.io/SPAM/>. Give it a minute after the last
commit.

You should see the filter coverage plot on the Overview tab and five working
tabs. If the page looks like plain unstyled text, `assets/style.css` did not
land in the right place — check the file list in the repo and confirm you have
folders named `assets`, `data` and `scripts` rather than loose files.

## What you can skip

`.nojekyll` is also a hidden file, but you do not need it. It only matters if
you later add a folder whose name starts with an underscore. Ignore it.

`SETUP.md` is documentation for you, not part of the site. Upload it or don't.
