# Agentic-J — landing page

Static, dependency-free landing page for the Agentic-J project. Designed
for GitHub Pages from a `gh-pages` branch.

## Files

```
website/
├── index.html          ← single-page site
├── css/styles.css      ← modern scientific dark theme
├── js/main.js          ← reveal-on-scroll, copy-code, scrollspy
├── assets/             ← logo + favicon (SVG)
├── images/             ← drop screenshots here (see SCREENSHOTS.md)
├── SCREENSHOTS.md      ← exact instructions for capturing screenshots
└── DEPLOY.md           ← three deploy options (manual / subtree / Actions)
```

## Local preview

```bash
cd website
python3 -m http.server 8080   # → http://localhost:8080
```

## Next steps

1. Read **[DEPLOY.md](DEPLOY.md)** and update `https://github.com/`
   placeholders to your actual repo URL.
2. Read **[SCREENSHOTS.md](SCREENSHOTS.md)** and capture the four
   screenshots referenced by the site. Drop them in `images/`.
3. Push to `gh-pages` (Option A) or set up the GitHub Action (Option C).
