# Deploying the website to GitHub Pages

The site is a plain static folder — no build step. We host it from a
dedicated `gh-pages` branch so the source branch stays clean.

There are two ways to deploy. Pick **one**.

---

## Option A — One-shot manual deploy (simplest)

Run this from the repository root **once you've replaced the GitHub link
placeholders** (see "Before you deploy" below):

```bash
# 1. Make sure you're on a clean working tree, on the source branch.
git status

# 2. Create a fresh gh-pages branch with the website contents at the root.
git switch --orphan gh-pages
git rm -rf .                          # clears the staged tree
cp -r website/. .                     # move site files to repo root
echo "agentic-j.example.com" > CNAME   # OPTIONAL custom domain
touch .nojekyll                       # disable Jekyll processing
git add -A
git commit -m "Publish website"
git push -u origin gh-pages

# 3. Switch back to your working branch.
git switch -
```

Then enable Pages in the GitHub UI:

1. **Repo → Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `gh-pages` · Folder: `/ (root)` · **Save**

After ~30 s your site is live at `https://<user>.github.io/<repo>/`.

For future updates: rebuild the orphan branch the same way, or use
Option B below for a less destructive flow.

---

## Option B — Recurring deploy via subtree (recommended for updates)

This keeps `gh-pages` as a separate branch but lets you update it from
`website/` on your main branch with a single command.

```bash
# First-time setup (creates the gh-pages branch from the website/ subtree)
git subtree push --prefix website origin gh-pages

# Subsequent updates
# 1) Edit files in website/ as normal.
# 2) Commit on your working branch.
# 3) Re-publish:
git subtree push --prefix website origin gh-pages
```

If `git subtree push` fails because of a non-fast-forward (you've rewritten
gh-pages history), force it like this:

```bash
git push origin `git subtree split --prefix website main`:gh-pages --force
```

---

## Option C — GitHub Actions (set-it-and-forget-it)

Add a workflow at `.github/workflows/pages.yml`:

```yaml
name: Publish website
on:
  push:
    branches: [main]
    paths: ['website/**', '.github/workflows/pages.yml']
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: website
      - id: deployment
        uses: actions/deploy-pages@v4
```

Then in **Settings → Pages**, switch **Source** to *GitHub Actions*. Every
push to `main` that touches `website/**` will auto-deploy.

---

## Before you deploy — link checklist

The HTML currently uses `https://github.com/` as a placeholder for every
GitHub link. Replace these in `website/index.html` once you know your
repo URL (e.g. `https://github.com/your-org/agentic-j`):

```bash
# from repo root
sed -i 's|https://github.com/|https://github.com/your-org/agentic-j|g' website/index.html
```

The doc-card links currently all point to `https://github.com/`. If you
want each card to deep-link into the right markdown guide, replace them
with paths like:

```
https://github.com/your-org/agentic-j/blob/main/user_guide/01_getting_started.md
https://github.com/your-org/agentic-j/blob/main/user_guide/02_interface_and_agents.md
…etc
```

Also update the Open Graph URL (`og:url` is not yet set — add it after
you have the canonical Pages URL).

---

## Local preview

The site is fully static; serve it locally with any of:

```bash
cd website
python3 -m http.server 8080         # → http://localhost:8080
# or
npx serve .                         # → http://localhost:3000
```

---

## Troubleshooting

| Symptom | Fix |
|--|--|
| 404 after deploy | Ensure `index.html` is at the **root** of the deployed branch, not under `website/`. Option A copies it there; Option B/C handle it via subtree/artifact. |
| Fonts missing | Google Fonts is loaded via `<link>` tag. CSS has system fallbacks if blocked. |
| Custom domain not working | The `CNAME` file must contain only the bare hostname, no protocol or path. DNS: add a `CNAME` record pointing to `<user>.github.io`. |
| Jekyll mangled output | Make sure `.nojekyll` exists at the root of the deployed branch. |
