# Word-list attribution

* `en.txt, es.txt, fr.txt, de.txt, it.txt, pt.txt, nl.txt, da.txt, sv.txt, no.txt, fi.txt, pl.txt, cs.txt, hu.txt, tr.txt, ru.txt`
  are **unmodified copies** of the per-language files from
  **List of Dirty, Naughty, Obscene, and Otherwise Bad Words** (LDNOOBW),
  <https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words>
  (downloaded 2026-10-04, upstream last commit 2020-07-13).
  Licence: **Creative Commons Attribution 4.0 International (CC BY 4.0)** - full text in `LICENSE-CC-BY-4.0.txt`.
  Attribution: "List of Dirty, Naughty, Obscene, and Otherwise Bad Words" by Shutterstock and contributors, CC BY 4.0.
  We did not change these files; our additions and exceptions live in the separate files below.
* `extra.txt`, `allow_words.txt`, `allow_phrases.txt`, `stems.txt` are original to ZEIM (no third-party licence).

Other permissively licensed sources considered but **not bundled** (could be added the same way): `better-profanity` (MIT),
`profanity-check` (MIT, ML model).  The lists are a first line of defence, not a complete moderation system: they miss new slang
and other languages, and any word list produces some false positives/negatives. Edit the `.txt` files to tune them - changes are
picked up without a restart (see `app/community/safety.py`).
