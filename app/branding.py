"""ALL product / section names live here (single place to rename).

Original names chosen to avoid third-party branding. Wordmark: static/logo.jpg (ZEIM). Sent to the browser via GET /api/config;
the UI has no hard-coded product names. (Trademark clearance has NOT been done - check before
public launch.) Third-party services in integrations (PrusaSlicer, OctoPrint, TikTok, ...) are
named factually, never as our feature names.
"""
PRODUCT_NAME = "ZEIM"
TAGLINE = "Turn photos into things you can hold"

SECTIONS = {
    "create": "Studio",             # build lithophanes / reliefs / pop-art
    "discover": "Showcase",         # community projects (all free)
    "learn": "Spark Lab",           # classroom-friendly education center
    "groups": "Build Plates",       # hobbyist groups (plural); singular below
    "edit": "Edit",                 # upload + modify existing 3D files
    "history": "Recent builds",
}
SHOWCASE_TABS = {"trending": "Trending", "free": "Newest", "foryou": "For You"}   # key "free" kept for stored data/API stability; everything is free anyway
GROUP_NAME = "Build Plate"          # one hobbyist group
GROUP_NAME_PLURAL = "Build Plates"  # hobbyist groups (not built yet - see ROADMAP)
