# Perplexity branch: integration verification

Verified 2026-10-18 against the actual ZEIM FastAPI app, not only a static mock.
Base: `zeim` at `c5aabcfbb2def4ce28681f6d9bce440025f96e53`.

## Automated tests

Python 3.13.12, installed using the repository's unchanged `requirements.txt` and
`constraints.txt`, plus pytest.

```sh
python -m pytest tests/test_perplexity_workbench.py tests/test_b2_static.py \
  tests/test_app.py tests/test_features.py tests/test_printer_profiles.py \
  tests/test_slice_api.py -q
# 80 passed, 2 skipped

python -m pytest tests/test_litho_shapes.py tests/test_litho_light.py \
  tests/test_litho_place.py tests/test_plate_editor.py tests/test_printer_security.py -q
# 86 passed

cd workbench/perplexity
npm ci
npm test
# 4 passed
npm run build
npm audit --omit=dev
# 0 reported vulnerabilities at verification time
```

Total: **166 Python tests passed, 2 skipped; 4 JavaScript geometry tests passed.**
This is a targeted regression set, not a claim that every repository test was run.
Existing FastAPI/Starlette deprecation warnings were observed.

The first GitHub Actions run reached Python collection but failed because the
`pytest` console entry point did not place the repository root on `sys.path`.
The workflow was corrected to use `python -m pytest`, matching the passing local
invocation; this is a CI launch-path correction, not a skipped or disabled test.

## Browser checks

Opened the real `/workbench/` route using a loopback-only uvicorn instance with fresh
temporary data/output directories. No production user data or accounts were used.

- All six presets and four mods exercised.
- Reversed thickness bounds block generation.
- Actual lithophane STL download was reimported into the STL viewer.
- Wireframe/solid and navigation controls checked.
- All three views inspected at desktop and 375 px mobile.
- Existing-logo/return link navigated back to the original `/` app.
- No uncaught page exceptions, CSP console errors or horizontal overflow were found in these flows.
- Self-hosted Manrope loaded successfully; no CDN/CSP relaxation was added.

Own-app captures:

- [Studio desktop](screenshots/studio-desktop.png)
- [Lithophane desktop](screenshots/litho-desktop.png)
- [Appearance desktop](screenshots/appearance-desktop.png)
- [Studio mobile](screenshots/studio-mobile.png)

These captures show the opt-in workbench page. They do not show all existing ZEIM
screens, verify competitor behavior or establish physical-print quality.

## Fresh REA observation

Pinned runtime: `rea-agents@6.5.0`, through the skill's checked launcher.
Target: actual ZEIM `http://127.0.0.1:8766/workbench/`.

Successful evidence:
`ev_cbab3a0f2e27e6d729e6bd2fc81e9815e4227e9c434d4c4fd658035ecae8dad8`.

All **20 declared actions** completed: readiness, appearance, Blueprint preset,
dark on/off, grid/inspector mods, studio, wireframe/solid, reset, lithophane,
width edit, invalid-thickness guard, recovery, and three image-preview modes.
The example scenario is committed in `workbench/perplexity/rea-scenario.example.json`;
set its Chromium executable path to your installed browser before replaying.

An initial scenario failed at an ambiguous readiness locator. That failed record
was retained; the successful run changed the locator to a unique test ID.
The manifest preserves both identities rather than relabeling the failed run.

## Source and security preservation

`static/index.html` SHA-256 remained:
`ae5438977b59826e2ef9ab8b29fa1486c7a6aeed830c463bfb52d9ef84e88b9f`.

Only `app/main.py` gained the opt-in route/redirect; original routes and middleware
retain their policies. No original editor/lithophane API implementation or Python
dependency pins were changed. Raw third-party browser content and cookies are not
committed. REA and ArtCraft are provenance/research references, not product services.
