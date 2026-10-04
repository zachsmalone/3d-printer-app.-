"""Chat language filter (PG-13) + the single gate for free text that other people can read.

If a message contains disallowed language the server REFUSES to send/store it and tells the sender:
    "Chat doesn't allow that language. Please use appropriate language."
There are no strikes, bans or restricted modes. Reporting, muting (teachers) and the moderator queue stay available.

Word lists are plain files in `app/community/wordlists/` (edit them any time; changes load without a restart):
  <lang>.txt          LDNOOBW lists (CC BY 4.0, see ATTRIBUTION.md) for en es fr de it pt nl da sv no fi pl cs hu tr ru
  extra.txt           ZEIM additions: slurs / hate speech / sexual terms / grooming-style phrases
  allow_words.txt     false-positive allowlist (Scunthorpe-style names, cross-language collisions, 3D-printing words)
  allow_phrases.txt   multi-word exceptions ("ball bearing")
  stems.txt           long distinctive stems that are also caught when run together / spaced out ("fu ck")
Matching is on WHOLE WORDS (so "class", "assemble", "cockpit", "Scunthorpe" are fine), with plural/-ing/-ed handling, leetspeak
("sh!t", "a55"), stretched letters ("fuuuck"), accents, and spaced-out letters ("f u c k", "f.u.c.k").
Non-English entries of 3 characters or fewer are ignored (too many collisions with ordinary words in other languages);
for CJK-style scripts without spaces substring matching is used.
Honest limits: a word list is not a moderation service - it misses new slang, context, images and most languages.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .identity import Actor

WL = Path(__file__).parent / "wordlists"
BLOCK_MESSAGE = "Chat doesn't allow that language. Please use appropriate language."
CONTACT_MESSAGE = "Chat doesn't allow sharing contact details or links. Please keep personal info private."

CANNED = {
    "talk_next_class": "I'd like to talk next class",
    "need_help": "I need help with my project",
    "finished": "I finished my project",
    "thanks": "Thank you!",
}
TEACHER_CANNED = ["talk_next_class", "thanks"]
STUDENT_CANNED = ["talk_next_class", "need_help", "finished", "thanks"]

_LEET = {"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g", "@": "a", "$": "s", "!": "i", "|": "i", "+": "t"}
MAX_SCAN_CHARS = 2000      # nothing longer is ever scanned (callers cap their own fields much lower); longer = refused
_EMAIL = re.compile(r"[\w.+-]{1,64}\s{0,3}(@|\(at\)|\[at\])\s{0,3}[\w-]{1,63}\s{0,3}(\.|\(dot\)|\[dot\])\s{0,3}\w{2,}", re.I)
_PHONE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)")
_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|io|gg|me|ly|tv|app|dev)\b)", re.I)
_HANDLE = re.compile(r"\b(snap(chat)?|insta(gram)?|discord|tiktok|whatsapp|kik|telegram)\b.{0,12}[:@ ]\s*[\w.]{3,}", re.I)
_NOSPACE_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\u0e00-\u0e7f\uac00-\ud7af]")


class ChatBlocked(Exception):
    def __init__(self, status: int, payload: dict):
        super().__init__(payload.get("message", ""))
        self.status, self.payload = status, payload


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _squeeze(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


class _Lists:
    def __init__(self):
        self.sig = None
        self.words: set[str] = set()
        self.phrases: set[tuple] = set()
        self.squeezed: set[str] = set()
        self.cjk: set[str] = set()
        self.allow_words: set[str] = set()
        self.allow_phrases: set[tuple] = set()
        self.stems: list[str] = []

    @staticmethod
    def _lines(p: Path):
        try:
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    yield _strip(ln)
        except OSError:
            return

    def load(self):
        files = sorted(WL.glob("*.txt"))
        sig = tuple((f.name, f.stat().st_mtime_ns) for f in files)
        if sig == self.sig:
            return self
        self.sig = sig
        aw = {w for w in self._lines(WL / "allow_words.txt")}
        self.allow_words = aw
        self.allow_phrases = {tuple(re.findall(r"\w+", p)) for p in self._lines(WL / "allow_phrases.txt")}
        self.stems = [s for s in self._lines(WL / "stems.txt") if len(s) >= 4]
        words, phrases, cjk = set(), set(), set()
        for f in files:
            if f.name in ("allow_words.txt", "allow_phrases.txt", "stems.txt"):
                continue
            lang = f.stem
            for ln in self._lines(f):
                toks = tuple(re.findall(r"\w+", ln))
                if not toks:
                    continue
                if _NOSPACE_SCRIPT.search(ln):
                    cjk.add(ln)
                    continue
                if lang not in ("en", "extra") and len(ln) <= 3:
                    continue                       # short foreign words collide with ordinary words
                if len(toks) == 1:
                    if toks[0] not in aw:
                        words.add(toks[0])
                else:
                    phrases.add(toks)
        self.words, self.phrases, self.cjk = words, phrases, cjk
        self.squeezed = {_squeeze(w) for w in words}
        return self


_L = _Lists()


def _leet_variants(chunk: str) -> list[str]:
    """Plain chunk plus a leet-decoded one (only when it mixes letters with digits/symbols)."""
    out = [chunk]
    if re.search(r"[a-z]", chunk) and re.search(r"[0-9@$!|+]", chunk):
        out.append("".join(_LEET.get(c, c) for c in chunk))
        if "1" in chunk:
            out.append("".join(_LEET.get(c, "i" if c == "1" else c) for c in chunk))
            out.append("".join(_LEET.get(c, "l" if c == "1" else c) for c in chunk))
    return out


_SUFFIXES = ("s", "es", "ed", "ing", "er", "ers", "y", "ies", "in")


def _forms(tok: str):
    yield tok
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4 - (suf in ("s", "es")):
            base = tok[:-len(suf)]
            yield base
            if len(base) > 3 and base[-1] == base[-2]:
                yield base[:-1]          # shitt-y -> shit
            if suf in ("y", "ies") and suf == "ies":
                yield base + "y"


def _token_hit(tok: str, L: _Lists) -> bool:
    if tok in L.allow_words or len(tok) < 2:
        return False
    for f in _forms(tok):
        if f in L.words and f not in L.allow_words:
            return True
    if re.search(r"(.)\1\1", tok):                         # stretched: fuuuuck
        sq = _squeeze(tok)
        if any(sq == s or sq == s + "s" for s in L.squeezed if len(s) >= 3):
            return True
    return False


def _words_in(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text)


def scan_language(text: str) -> str | None:
    """'language' if the text contains disallowed words, else None."""
    L = _L.load()
    base = _strip(text or "")
    if not base.strip():
        return None
    for cjk in L.cjk:
        if cjk in base:
            return "language"
    chunks = base.split()
    variants = []
    for v in range(4):                         # plain, leet, leet(1=i), leet(1=l)
        parts = []
        for ch in chunks:
            vs = _leet_variants(ch)
            parts.append(vs[v] if v < len(vs) else ch)
        variants.append(" ".join(parts))
    for var in dict.fromkeys(variants):
        toks = _words_in(var)
        # join runs of >=3 single-letter tokens: "f u c k", "f.u.c.k"
        joined, run = [], []
        for t in toks + [""]:
            if len(t) == 1 and t.isalpha():
                run.append(t)
                continue
            if len(run) >= 3:
                joined.append("".join(run))
            else:
                joined.extend(run)
            run = []
            if t:
                joined.append(t)
        toks = joined
        # remove allow-phrases
        for ph in L.allow_phrases:
            n = len(ph)
            i = 0
            while i <= len(toks) - n:
                if tuple(toks[i:i + n]) == ph:
                    del toks[i:i + n]
                else:
                    i += 1
        if any(_token_hit(t, L) for t in toks):
            return "language"
        for ph in L.phrases:
            n = len(ph)
            if any(tuple(toks[i:i + n]) == ph for i in range(len(toks) - n + 1)):
                return "language"
        # glued / split evasions: long stems inside the letters-only text (allowlisted words masked out first)
        letters = "".join(t for t in toks if t not in L.allow_words)
        flat = _squeeze(letters) if re.search(r"(.)\1\1", letters) else letters
        if any(s in letters or s in flat or _squeeze(s) in flat for s in L.stems):
            return "language"
    return None


def scan_contact(text: str) -> str | None:
    t = (text or "").lower()
    if _EMAIL.search(t) or _PHONE.search(t) or _URL.search(t) or _HANDLE.search(t):
        return "contact_info"
    return None


def scan(text: str) -> str | None:
    if len(text or "") > MAX_SCAN_CHARS:
        return "too_long"
    return scan_language(text) or scan_contact(text)


def check(text: str, context: str = "") -> str:
    """Return the cleaned text, or raise ChatBlocked(422) with the user-facing message. Nothing is stored/sent on a block."""
    text = (text or "").strip()
    r = scan(text)
    if r == "too_long":
        raise ChatBlocked(413, {"code": "too_long", "message": "That text is too long. Please make it shorter.", "context": context})
    if r:
        msg = BLOCK_MESSAGE if r == "language" else CONTACT_MESSAGE
        raise ChatBlocked(422, {"code": "language_blocked" if r == "language" else "contact_blocked",
                                "message": msg, "context": context})
    return text


def gate(actor: Actor, text: str, context: str) -> str:
    """Single entry point for every free-text field other people can read (feedback, titles, descriptions, nicknames…)."""
    return check(text, context)


def filter_only(text: str, what: str) -> str:
    try:
        return check(text, what)
    except ChatBlocked as e:
        raise ValueError(e.payload["message"])
