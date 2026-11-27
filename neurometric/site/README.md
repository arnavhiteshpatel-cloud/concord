# NeuroMetric website

Static site: plain HTML, one stylesheet (`assets/css/site.css`), one small progressive-enhancement
script (`assets/js/site.js`, collapses the menu on narrow screens). No build step, no cookies, no
analytics or trackers, no external fonts, scripts or forms. Icons are inline SVG.

## Preview

From the `neurometric/` directory:

```sh
python -m http.server -d site
```

Then open <http://localhost:8000/>.

## Pages

| File | Content |
|---|---|
| `index.html` | The scientific problem (device operation is not meaningful benefit), the measurement chain, who it serves |
| `approach.html` | Task battery, simulated-decoder harness, home-use logging, care-partner capture, evidence packaging, what it never does |
| `modalities.html` | Supported experimental input modalities and their testing status |
| `research.html` | Limitations (first), computational programme, summary statistics, metric definitions, simulation methods |
| `results.html` | **Generated** by `build_results.py`; do not edit by hand |
| `privacy.html` | What the website and the research software do and do not collect |
| `status.html` | Development status table |
| `collaborate.html` | Collaboration opportunities and contact (placeholder email) |
| `demo.html` | How to run the local interactive demo; screenshot block is refreshed by `build_results.py` |

The header and footer are repeated in every page. If you change the navigation, change it in
every `*.html` file (except `results.html`, which copies the header and footer from `index.html`
when regenerated; keep the `<!-- BEGIN:main -->` / `<!-- END:main -->` markers in `index.html`).

## Regenerate the results page

```sh
python site/build_results.py
```

Standard library only; safe to re-run whenever experiments finish. It:

* reads every `experiments/results/<EXP>/summary.json` (falling back to a JSON file in that folder
  with an `"experiment"` key when there is no `summary.json`);
* copies each experiment's figures into `site/assets/results/<exp>/` (stale copies are removed);
* writes `site/results.html`, labelling every result set as simulation, real public data, or
  "provenance not recorded" from its `synthetic` field;
* refreshes the screenshot block in `demo.html` from images in any `screenshots/` folder under
  `web/` or `experiments/`, or in `web/public/demo/` (copied to `site/assets/demo/`).

A `summary.json` may optionally include `"title"`, `"description"` and
`"figures": {"file.png": "alt text"}` to improve its section. Figures without supplied alt text
get generic alt text; add real descriptions for new figures (see `KNOWN_FIGURE_ALT` in the script).

## Accessibility checks

Every page was checked with axe-core 4.10 (WCAG 2.0/2.1/2.2 A and AA rules plus best practices) in
headless Chrome via Playwright, in both light and dark colour schemes, with 0 violations, and for
horizontal overflow at 360 px and 390 px widths. Full-page screenshots of the home page at
1280 px and 390 px are in `screenshots/`. Automated checks do not replace testing with
screen-reader, switch, eye-gaze and keyboard-only users.

## Before publishing (founder TODO)

* Replace the placeholder `hello@example.com` in `collaborate.html` (marked TODO on the page).
* Re-run `python site/build_results.py` after the experiment runs finish.
* Check `modalities.html` (the gamepad row; its adapter landed while the site was being built) and `demo.html` (run commands) against the current
  state of `web/` and the repository README.
* Keep claims in step with `EVIDENCE_LEDGER.md`, `BLOCKERS.md` and the status table. Do not add
  logos, testimonials, partner names or metrics that do not exist.
* Have the privacy page reviewed by counsel or an IRB before any study use.
