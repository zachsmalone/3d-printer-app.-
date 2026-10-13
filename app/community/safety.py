"""Chat language filter (PG-13) + the single gate for free text that other people can read.

If a message contains disallowed language the server REFUSES to send/store it and tells the sender:
    "Chat doesn't allow that language. Please use appropriate language."
There are no strikes, bans or restricted modes. Reporting, and the moderator queue stay available.

Word lists are plain files in `app/community/wordlists/` (edit them any time; changes load without a restart):
  <lang>.txt          LDNOOBW lists (CC BY 4.0, see ATTRIBUTION.md) for en es fr de it pt nl da sv no fi pl cs hu tr ru
  extra.txt           ZEIM additions: slurs / hate speech / sexual terms / grooming-style phrases
                     (plus a regex pattern layer in scan_grooming for common rewordings)
  allow_words.txt     false-positive allowlist (Scunthorpe-style names, cross-language collisions, 3D-printing words)
  allow_phrases.txt   multi-word exceptions ("ball bearing")
  stems.txt           long distinctive stems that are also caught when run together / spaced out ("fu ck")
ONE normalisation pipeline (`normalize`) is applied to the word lists, to every scan and to the contact-info checks: NFKC, accents and
all invisible/format characters removed (zero-width, soft hyphen, tags, bidi, variation selectors), Cyrillic/Greek/small-caps/squared
look-alikes mapped to Latin, other-script digits to 0-9, lower-case.
Matching is on WHOLE WORDS (so "class", "assemble", "cockpit", "Scunthorpe", "Nigeria" are fine), with plural/-ing/-ed handling, leetspeak
("sh!t", "a55"), stretched letters ("fuuuck"), spaced-out letters ("f u c k", "f.u.c.k") and a single inserted symbol ("f*ck", "fu.ck").
Contact checks also refuse digits hidden with invisible characters ("555<zero-width>1234"), phone numbers typed digit-by-digit or spelled
out (incl. "triple five", "fivefivefive"; plain counting "one two three ... seven" is allowed), and disguised platform names ("d1scord: name").
Only the files listed in LANG_FILES / EXTRA_FILES / ALLOW_FILES are read - the CC-BY licence text in the same folder is NOT a word list.
If the required lists are missing the filter FAILS CLOSED: free text is refused (HTTP 503) instead of letting everything through.
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
LANG_FILES = ("en", "es", "fr", "de", "it", "pt", "nl", "da", "sv", "no", "fi", "pl", "cs", "hu", "tr", "ru")
EXTRA_FILES = ("extra",)
ALLOW_FILES = ("allow_words", "allow_phrases", "stems")
REQUIRED = ("en", "extra")            # if either is missing/empty the filter refuses text instead of passing everything
UNAVAILABLE_MESSAGE = "Posting text is paused for a moment. Please try again later."
BLOCK_MESSAGE = "Chat doesn't allow that language. Please use appropriate language."
CONTACT_MESSAGE = "Please don't put names, phone numbers, emails or links here."



MAX_SCAN_CHARS = 2000      # nothing longer is ever scanned (callers cap their own fields much lower); longer = refused
_LEET = {"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g", "@": "a", "$": "s", "!": "i", "|": "i", "+": "t"}
_NOSPACE_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\u0e00-\u0e7f\uac00-\ud7af]")


class ChatBlocked(Exception):
    def __init__(self, status: int, payload: dict):
        super().__init__(payload.get("message", ""))
        payload.setdefault("detail", payload.get("message", ""))       # same shape everywhere: code, message, context, detail
        self.status, self.payload = status, payload


# ------------------------------------------------------------------------------------------------ normalisation
def _build_confusables() -> dict:
    m = {}
    pairs = {  # Cyrillic
        "а": "a", "в": "b", "е": "e", "ё": "e", "з": "3", "і": "i", "ї": "i", "ј": "j", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
        "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ѵ": "v", "ӏ": "l", "ь": "b", "ѡ": "w",
        # Greek
        "α": "a", "β": "b", "γ": "y", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "η": "n", "ω": "w",
        "ϲ": "c", "ϳ": "j", "μ": "u",
        # Latin look-alikes that NFKC/NFKD do not fold
        "ł": "l", "ø": "o", "đ": "d", "ı": "i", "ħ": "h", "ŧ": "t", "ƀ": "b", "ǥ": "g", "ɑ": "a", "ɘ": "e", "ſ": "s", "ɡ": "g", "ƒ": "f",
        "ɗ": "d", "ɠ": "g", "ʜ": "h", "ꞁ": "l", "ǀ": "l", "ꓲ": "i",
    }
    m.update(pairs)
    for ch, lat in zip("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ", "abcdefghijklmnopqrstuvwxyz"):     # small caps
        m[ch] = lat
    for base in (0x1F130, 0x1F150, 0x1F170, 0x1F1E6):                                    # squared / negative circled / negative squared / regional
        for i in range(26):
            m[chr(base + i)] = chr(97 + i)
    return m


_CONF = _build_confusables()
_BLANKS = {"\u3164", "\u115f", "\u1160", "\uffa0", "\u2800", "\u180e"}             # "invisible" letters that are not category Cf/Mn


def normalize(s: str) -> str:
    """The single pipeline used for word lists, language scans and contact checks (see module docstring)."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me", "Cf") or ch in _BLANKS:
            continue                                    # accents, zero-width, soft hyphen, tags, bidi marks, variation selectors
        if cat == "Nd" and not ch.isascii():
            ch = str(unicodedata.digit(ch, 0))          # other scripts' digits -> 0-9
        out.append(_CONF.get(ch, ch))
    return "".join(out)


_strip = normalize          # (old name, still used by a few callers)


def _squeeze(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def _halve(w: str) -> str | None:
    """'ffuucckk' -> 'fuck' when EVERY letter is doubled."""
    if len(w) >= 6 and len(w) % 2 == 0 and all(w[i] == w[i + 1] for i in range(0, len(w), 2)):
        return w[::2]
    return None


# ------------------------------------------------------------------------------------------------ word lists
class _Lists:
    def __init__(self):
        self.sig = None
        self.ok = False
        self.words: set[str] = set()
        self.phrases: set[tuple] = set()
        self.squeezed: set[str] = set()
        self.cjk: set[str] = set()
        self.allow_words: set[str] = set()
        self.allow_phrases: set[tuple] = set()
        self.stems: list[str] = []
        self.by_len: dict[int, list[str]] = {}

    @staticmethod
    def _lines(p: Path):
        try:
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    yield normalize(ln)
        except OSError:
            return

    def load(self):
        try:
            intended = [WL / f"{n}.txt" for n in LANG_FILES + EXTRA_FILES + ALLOW_FILES]
            sig = tuple((f.name, f.stat().st_mtime_ns if f.exists() else 0) for f in intended)
        except OSError:
            sig = ("missing",)
        if sig == self.sig:
            return self
        self.sig = sig
        aw = set(self._lines(WL / "allow_words.txt"))
        self.allow_words = aw
        self.allow_phrases = {tuple(re.findall(r"\w+", p)) for p in self._lines(WL / "allow_phrases.txt")}
        self.stems = [s for s in self._lines(WL / "stems.txt") if len(s) >= 4]
        words, phrases, cjk = set(), set(), set()
        counts = {}
        for lang in LANG_FILES + EXTRA_FILES:
            f = WL / f"{lang}.txt"
            n = 0
            for ln in self._lines(f):
                toks = tuple(re.findall(r"\w+", ln))
                if not toks:
                    continue
                n += 1
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
            counts[lang] = n
        self.words, self.phrases, self.cjk = words, phrases, cjk
        self.squeezed = {_squeeze(w) for w in words}
        self.by_len = {}
        for w in words:
            self.by_len.setdefault(len(w), []).append(w)
        self.ok = all(counts.get(r, 0) >= 20 for r in REQUIRED)       # fail closed if the main lists are missing/empty
        if not self.ok:
            import logging
            logging.getLogger("zeim").error("language filter word lists missing or empty in %s: refusing free text until fixed", WL)
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
            if suf == "ies":
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
    h = _halve(tok)
    return bool(h and h not in L.allow_words and any(f in L.words for f in _forms(h)))


def _words_in(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text)


_WILD = re.compile(r"[*#_%^~?]")


def _stem_hit(letters: str, L: _Lists) -> bool:
    """Stems are matched INSIDE ONE chunk of letters only (never across words), squeezed only when the text really is stretched."""
    if not letters:
        return False
    if any(s in letters for s in L.stems):
        return True
    flat = None
    if re.search(r"(.)\1\1", letters):
        flat = _squeeze(letters)
    else:
        h = _halve(letters)
        flat = h if h else None
    return bool(flat and any(s in flat or _squeeze(s) in flat for s in L.stems))


def _scan_view(var: str, L: _Lists) -> bool:
    chunks = var.split()
    for ch in chunks:
        toks_c = _words_in(ch)
        if not toks_c:
            continue
        # one symbol inserted/replacing a letter: "fu.ck", "f-u-c-k", "f*ck"
        if len(toks_c) >= 2 and re.search(r"[a-z0-9][^a-z0-9\s][a-z0-9]", ch):
            coll = "".join(toks_c)
            if coll not in L.allow_words and _token_hit(coll, L):
                return True
        if _WILD.search(ch.strip("*#_%^~?")) and 4 <= len(ch.strip("*#_%^~?")) <= 20:
            core = ch.strip("*#_%^~?").replace("?", "*")
            pat = re.compile("".join("." if c in "*#_%^~" else re.escape(c) for c in core if c.isalnum() or c in "*#_%^~"))
            n = len(pat.pattern) and sum(1 for c in core if c.isalnum() or c in "*#_%^~")
            if n and any(pat.fullmatch(w) for w in L.by_len.get(n, ()) if w[0] == core[0] and w not in L.allow_words):
                return True
        letters = "".join(t for t in toks_c if t not in L.allow_words and not t.isdigit()) if len(toks_c) > 1 else \
            ("".join(c for c in toks_c[0] if c.isalpha()) if toks_c[0] not in L.allow_words else "")
        if _stem_hit(letters, L):
            return True
    # runs of tiny chunks: "f u c k", "fu ck", "f u ck"
    run = []
    for ch in chunks + [""]:
        lt = "".join(c for c in ch if c.isalpha())
        if ch and 1 <= len(lt) <= 2 and len(_words_in(ch)) == 1:
            run.append(lt)
            continue
        if len(run) >= 2:
            j = "".join(run)
            if len(j) >= 4 and (_token_hit(j, L) or _stem_hit(j, L)):
                return True
        run = []
    toks = _words_in(var)
    joined, run = [], []
    for t in toks + [""]:                       # join runs of >=3 single-letter tokens: "f u c k", "f.u.c.k"
        if len(t) == 1 and t.isalpha():
            run.append(t)
            continue
        joined.extend(["".join(run)] if len(run) >= 3 else run)
        run = []
        if t:
            joined.append(t)
    toks = joined
    for ph in L.allow_phrases:                  # remove allow-phrases
        n = len(ph)
        i = 0
        while i <= len(toks) - n:
            if tuple(toks[i:i + n]) == ph:
                del toks[i:i + n]
            else:
                i += 1
    if any(_token_hit(t, L) for t in toks):
        return True
    for ph in L.phrases:
        n = len(ph)
        if any(tuple(toks[i:i + n]) == ph for i in range(len(toks) - n + 1)):
            return True
    return False


def scan_language(text: str) -> str | None:
    """'language' if the text contains disallowed words, 'unavailable' if the word lists are missing (fail closed), else None."""
    L = _L.load()
    base = normalize(text or "")
    if not base.strip():
        return None
    if not L.ok:
        return "unavailable"
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
        if _scan_view(var, L):
            return "language"
    if "\u0443" in (text or "").lower():                       # Cyrillic у looks like y but is often used for u ("f" + у + "ck")
        return scan_language(text.lower().replace("\u0443", "u"))
    return None



# ------------------------------------------------------------------------------------------------ grooming / solicitation patterns
# Catches common rewordings of the child-safety phrases in extra.txt. Runs on normalised text.
# Honest limit: context-free patterns miss clever paraphrases; reports stay the primary control.
# Benign maker talk ("what age group is this lesson for", "where do I find the infill", "send me the STL")
# is written to pass — patterns require a YOU/YOUR-style target or a secrecy/isolation cue.

_YOU = r"(?:you|u|ya|your|ur|youre|you're)"
_PARENTS = r"(?:parents?|mom|mum|dad|mother|father|teacher|guardian)"
_AGE_ASK = re.compile(
    r"\b(?:how|what|hw|wut)\s+(?:old|age)\s+(?:are|r)\s+" + _YOU + r"\b"
    r"|\bwhat\s+(?:is|s)\s+" + _YOU + r"r?\s+age\b"
    r"|\b" + _YOU + r"r?\s+age\s*\?"
    r"|\b(?:what|which)\s+grade\s+(?:are|r)\s+" + _YOU + r"\b"
    r"|\b(?:when|whats|what's)\s+(?:is\s+)?" + _YOU + r"r?\s+birthday\b"
    r"|\basl\b|\ba\s*/\s*s\s*/\s*l\b"
    r"|\bare\s+" + _YOU + r"\s+(?:a\s+)?(?:boy|girl|guy|teen)\b",
    re.I,
)
_LOC_ASK = re.compile(
    r"\bwhere\s+(?:do|d)\s+" + _YOU + r"\s+live\b"
    r"|\bwhere\s+(?:are|r)\s+" + _YOU + r"\s+from\b"
    r"|\bwhat\s+(?:city|town|state|zip|address)\s+(?:are|r|do)\s+" + _YOU + r"\b"
    r"|\b(?:what|which)\s+school\s+(?:do|are|r)\s+" + _YOU + r"\b"
    r"|\b" + _YOU + r"r?\s+(?:real\s+)?(?:last\s+)?name\s*\?",
    re.I,
)
_SECRECY = re.compile(
    r"\b(?:don'?t|dont|do\s+not)\s+tell\s+(?:(?:your|ur)\s+)?" + _PARENTS + r"\b"
    r"|\bour\s+little\s+secret\b"
    r"|\bkeep\s+(?:this|it)\s+(?:a\s+)?secret\b"
    r"|\bkeep\s+(?:this|it)\s+between\s+us\b"
    r"|\b(?:no\s+one|nobody)\s+(?:has\s+)?to\s+know\b"
    r"|\bare\s+(?:your|ur)\s+" + _PARENTS + r"\s+home\b"
    r"|\bis\s+anyone\s+home\b"
    r"|\bdelete\s+(?:this|that)\s+(?:message|chat|text)\b",
    re.I,
)
_PIC_MEET = re.compile(
    r"\bsend\s+(?:me\s+)?(?:a\s+)?(?:pic|pics|picture|pictures|photo|photos|selfie)(?:\s+of\s+(?:yourself|you|u))?\b"
    r"|\bshow\s+me\s+" + _YOU + r"r?\s+face\b"
    r"|\bturn\s+on\s+" + _YOU + r"r?\s+camera\b"
    r"|\bwhat\s+are\s+" + _YOU + r"\s+wearing\b"
    r"|\bmeet\s+(?:me\s+)?(?:in\s+person|alone|after\s+school)\b"
    r"|\bcome\s+to\s+(?:my|our)\s+(?:house|place)\b"
    r"|\bcan\s+we\s+meet\b",
    re.I,
)
_OFF_PLATFORM = re.compile(
    r"\b(?:let'?s|lets|let\s+us)\s+(?:go\s+)?private\b"
    r"|\b(?:talk|chat|message)\s+(?:somewhere\s+)?(?:else|elsewhere)\b"
    r"|\bthis\s+chat\s+is\s+monitored\b",
    re.I,
)


def scan_grooming(text: str) -> str | None:
    """'language' if the text matches a grooming/solicitation pattern, else None.

    Exact multi-word phrases also live in extra.txt (caught by scan_language). This layer
    catches common rewordings on the same normalised text the rest of the filter uses.
    """
    t = normalize(text or "")
    if not t.strip():
        return None
    if (_AGE_ASK.search(t) or _LOC_ASK.search(t) or _SECRECY.search(t)
            or _PIC_MEET.search(t) or _OFF_PLATFORM.search(t)):
        return "language"
    return None


# ------------------------------------------------------------------------------------------------ contact info / PII
_BARE_TLD = r"(?:com|net|org|edu|gov|info|biz|xyz|ru|uk|co|us|ca|de|fr|cn|jp|au|link|site|online|club|shop|store)"
_STRONG_TLD = r"(?:com|net|org|edu|gov|info|biz|xyz|io|gg|ly|tv|ai|cc|app|dev|link|site|online)"
_DOTW = r"(?:\s{0,3}(?:\(dot\)|\[dot\]|\{dot\}|<dot>)\s{0,3}|\s+(?:dot|punto|point|punkt)\s+|-dot-)"   # the word "dot" in a few languages
_DOT_SP = r"(?:\s{0,3}\.\s{0,3}|" + _DOTW[3:]                                    # a literal dot with spaces, or the word
_DOT_TIGHT = r"(?:\.|" + _DOTW[3:]                                                # a literal dot WITHOUT spaces, or the word
_AT = r"(?:@|\(at\)|\[at\]|\{at\}|<at>)"
_AT_WORD = r"(?:\s{1,3}(?:at|arroba|arobase|aroba)\s{1,3}|\s{0,3}(?:\(at\)|\[at\]|\{at\}|<at>)\s{0,3}|-at-)"
_PROVIDERS = r"(?:gmail|yahoo|hotmail|outlook|icloud|protonmail|proton|aol|msn|gmx)"
_EMAIL_PLAIN = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{2,}){1,3}|@" + _PROVIDERS + r"\b")
_EMAIL_SPACED = re.compile(r"[\w.+-]{1,64}\s{0,3}" + _AT + r"\s{0,3}[\w-]{1,63}" + _DOT_SP + _STRONG_TLD + r"\b")
_EMAIL_WORDS = re.compile(r"[\w.+-]{1,64}" + _AT_WORD + r"[\w-]{1,63}" + _DOT_TIGHT + _BARE_TLD + r"\b")
_EMAIL_PROVIDER = re.compile(r"(?:\b(?:at|is)\s+[a-z0-9_.]{3,}|:\s*[a-z0-9_.]{3,}|\b[a-z_.]*\d[a-z0-9_.]*)\s+" + _PROVIDERS + r"\s+(?:com|net|co)\b|\bat\s+" + _PROVIDERS + r"\b|\b" + _PROVIDERS + r"\s*:\s*[a-z0-9_.]{4,}|\bmy\s+" + _PROVIDERS + r"\s+(?:is|address is)\s+[a-z0-9_.]{4,}")
_URL = re.compile(r"(?:\b(?:https?|ftp)://|\bwww\s*\.|\b(?:javascript|vbscript|data):|\blocalhost:\d|\b[a-z0-9][a-z0-9-]*\." + _BARE_TLD + r"\b|\b[a-z0-9-]+" + _DOTW + r"(?:" + _BARE_TLD + r"|io|gg)"
                  + r"\b|\b[a-z0-9-]{2,}\s+\.\s+" + _BARE_TLD + r"\b|\b[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}/[\w~%-]"
                  + r"|(?<![\d.])(?:[1-9]\d|1\d\d|2[0-4]\d|25[0-5])(?:\.\d{1,3}){3}(?![\d.]))")
_HANDLE_AT = re.compile(r"(?<![\w@.+-])@[a-z][a-z0-9_.]{2,30}|(?<![\w/])u/[a-z0-9_-]{3,}")
_HANDLE_TAG = re.compile(r"\b[a-z0-9_.]{2,32}#\d{4}\b")
_PLATFORMS = (r"(?:snapchat|snap|instagram|insta|tiktok|discord|whatsapp|telegram|kik|skype|twitter|facebook|roblox|"
              r"sc|ig|fb|yt|youtube|twitch|steam|reddit|wechat|minecraft|xbox|gamertag|username)")
_HANDLE_PLATFORM = re.compile(r"\b" + _PLATFORMS + r"\b\s*(?:[:@=]|\bid\b|\bhandle\b|\busername\b|add me|me on)\s*@?[a-z0-9_.]{3,}"
                              r"|\bmy\s+" + _PLATFORMS + r"\s+(?:is|username is|id is|handle is)\s+@?[a-z0-9_.]{3,}")
_ADD_ME = re.compile(r"\b(?:add|follow|find|message|msg|dm|hit|hmu|text)\s+me\s+(?:on|at|via)\s+" + _PLATFORMS + r"\b|\b(?:snap|snapchat|whatsapp|insta|instagram|kik|telegram|discord)\s+me\b|\bdm\s+me\b")
_PLATFORM_RE = re.compile(_PLATFORMS + r"$")
_HANDLE_AFTER_PLATFORM = re.compile(r"\b" + _PLATFORMS + r"\s+(?:gamertag\s+|tag\s+|name\s+)?(?=[a-z0-9_.]*[a-z]{2})(?=[a-z0-9_.]*\d)[a-z0-9_.]{4,30}\b"
                                    r"|\b(?:pm|facetime|skype|telegram|signal)\s+me\b")
_PLAT_LEET = str.maketrans({"1": "i", "0": "o", "3": "e", "4": "a", "5": "s", "@": "a", "$": "s", "!": "i"})


def _platform_view(t: str) -> str:
    """Spell platform names back out so the handle checks see them: 's n a p' / 's.n.a.p' -> 'snap', 'd1scord' -> 'discord'."""
    t = re.sub(r"(?<![a-z0-9])(?:[a-z][ .]){2,}[a-z](?![a-z0-9])",
               lambda m: (lambda j: j if _PLATFORM_RE.match(j) else m.group(0))(re.sub(r"[ .]", "", m.group(0))), t)
    return re.sub(r"(?<![a-z0-9])[a-z0-9@$!]{2,10}(?![a-z0-9])",
                  lambda m: (lambda j: j if _PLATFORM_RE.match(j) else m.group(0))(m.group(0).translate(_PLAT_LEET)), t)


_SEP = r"[ .\-/_,·]"
_PHONE_US = re.compile(r"(?<![\d.])(?:\+?\d{1,3}" + _SEP + r")?\(?\d{3}\)?" + _SEP + r"\d{3}" + _SEP + r"\d{4}(?![\d])")
_PHONE_INTL = re.compile(r"\+\d{1,3}[ .-]?\d{1,4}(?:[ .-]?\d{2,4}){2,4}(?!\d)")
_PHONE_GROUPS = re.compile(r"(?<![\d.])0\d{1,4}(?:" + _SEP + r"\d{2,4}){3,5}(?![\d.])|(?<![\d.])\d{2,4}(?:-\d{2,4}){4,5}(?![\d.-])|(?<!\d)0\d{3,4}[ -]\d{5,7}(?!\d)")
_PHONE_LOCAL = re.compile(r"\b(?:call|phone|text|tel|telephone|ring|dial|whatsapp|reach|contact|cell|mobile|my\s+(?:phone\s+|cell\s+)?(?:number|num|no))\b.{0,15}?(?<![\d])(?:\d{3}[ -]\d{4}|\d{7,11})(?!\d)")
_ADDRESS = re.compile(r"\b\d{1,5}\s+(?:[a-z]+\.?\s+){1,3}(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|highway|hwy)\b\.?")
_PO_BOX = re.compile(r"\bp\.?\s?o\.?\s?box\s+\d+")
_NUMWORDS = {w: 1 for w in (
    "zero oh one two three four five six seven eight nine "
    "cero uno dos tres cuatro cinco seis siete ocho nueve "
    "un une deux trois quatre cinq sept huit neuf "
    "null eins zwei drei vier funf sechs sieben acht neun").split()}


_NUMWORD_VAL = {w: str(i % 10) for i, grp in enumerate((
    "zero oh cero null", "one uno un une eins", "two dos deux zwei", "three tres trois drei", "four cuatro quatre vier",
    "five cinco cinq funf", "six seis sechs", "seven siete sept sieben", "eight ocho huit acht", "nine nueve neuf neun")) for w in grp.split()}
_REPEAT = {"double": 2, "triple": 3}


def _glued_numwords(tok: str) -> list[str] | None:
    """'fivefivefive' -> ['five', 'five', 'five'] when a token is made ONLY of 2+ number words, else None."""
    if len(tok) < 6 or tok in _NUMWORDS:
        return None
    best: dict[int, list[str]] = {0: []}
    for i in range(len(tok)):
        if i not in best:
            continue
        for w in _NUMWORD_VAL:
            if tok.startswith(w, i) and (i + len(w)) not in best:
                best[i + len(w)] = best[i] + [w]
    out = best.get(len(tok))
    return out if out and len(out) >= 2 else None


def _is_counting(digits: str) -> bool:
    """'1234567' / '0123456789' / '9876543': someone counting or a number stencil, not a phone number."""
    steps = {(int(b) - int(a)) for a, b in zip(digits, digits[1:])}
    return steps in ({1}, {-1})


def _spelled_number_run(t: str) -> bool:
    """>=7 digits written as words (any mix with short digit groups): 'five five five one two three four', 'triple five ...',
    'fivefivefive onetwothree'. Plain counting ('one, two, three ... seven') is not a phone number."""
    digits, words, mult = "", 0, 1

    def done() -> bool:
        return bool(words and len(digits) >= 7 and not _is_counting(digits))

    for m in re.finditer(r"[a-z]+|\d+", t):
        tok = m.group(0)
        parts = [tok] if tok in _NUMWORDS else _glued_numwords(tok)
        if tok in _REPEAT:
            mult = _REPEAT[tok]
            continue
        if parts:
            for w in parts:
                digits += _NUMWORD_VAL.get(w, "0") * mult; words += 1; mult = 1
        elif tok.isdigit() and len(tok) <= 4:
            digits += tok * mult; mult = 1
        else:
            if done():
                return True
            digits, words, mult = "", 0, 1
    return done()


_DIGIT_RUN = re.compile(r"\d(?:[\x00 .\-/_,·]{0,3}\d){6,}")


def _hidden_or_spaced_digits(raw: str) -> bool:
    """Phone numbers disguised with invisible characters between the digits ('555<zero-width>1234') or typed one digit at a
    time ('5 5 5 1 2 3 4 5 6 7'). Ordinary numbers never contain invisible characters, so any 7+ digit run that does is refused."""
    s = unicodedata.normalize("NFKC", raw or "")
    s = "".join("\x00" if (unicodedata.category(c) == "Cf" or c in _BLANKS) else c for c in s)
    for m in _DIGIT_RUN.finditer(s):
        run = m.group(0)
        digits = re.sub(r"\D", "", run)
        if _is_counting(digits):
            continue
        if "\x00" in run:
            return True
        if len(digits) >= 10 and len(set(digits)) > 2 and re.fullmatch(r"\d(?: \d){9,}", run):         # every digit on its own: 5 5 5 1 2 3 4 5 6 7
            return True
    return False


def _spaced_email(t: str) -> bool:
    """'n a m e @ g m a i l . c o m': letters spread out with spaces around an @ - closed up, does it read as an address on a real provider/TLD?"""
    if "@" not in t:
        return False
    d = re.sub(r"\s+", "", t)
    m = re.search(r"[\w.+-]{1,64}@([\w-]{1,63})\.(" + _STRONG_TLD[3:] + r"\b", d)
    return bool(m)


def _contact_view(t: str) -> bool:
    t = re.sub(r"\[\.\]|\(\.\)|[。｡]", ".", t).replace("hxxp", "http")         # "example[.]com", "example。com", "hxxps://"
    return bool(_EMAIL_PLAIN.search(t) or _EMAIL_SPACED.search(t) or _EMAIL_WORDS.search(t) or _EMAIL_PROVIDER.search(t)
            or _URL.search(t) or _PHONE_US.search(t) or _PHONE_INTL.search(t) or _PHONE_GROUPS.search(t) or _PHONE_LOCAL.search(t)
            or _spelled_number_run(t) or _HANDLE_AT.search(t) or _HANDLE_TAG.search(t) or _HANDLE_PLATFORM.search(t) or _ADD_ME.search(t) or _spaced_email(t)
            or _ADDRESS.search(t) or _PO_BOX.search(t) or _off_platform_handle(t))


def _off_platform_handle(t: str) -> bool:
    """'insta coolkid99', 'xbox gamertag coolkid99', 'pm me', and the platform-name disguises 'd1scord: name', 's n a p name'."""
    if _HANDLE_AFTER_PLATFORM.search(t):
        return True
    pv = _platform_view(t)
    return pv != t and bool(_HANDLE_PLATFORM.search(pv) or _ADD_ME.search(pv) or _HANDLE_AFTER_PLATFORM.search(pv)
                            or re.search(r"\b" + _PLATFORMS + r"\s+[a-z0-9_.]{4,30}\b", pv))


def scan_contact(text: str) -> str | None:
    raw = text or ""
    if _hidden_or_spaced_digits(raw):
        return "contact_info"
    views = [normalize(raw)]
    if any(unicodedata.category(c) == "Cf" or c in _BLANKS for c in raw):
        # an invisible character used AS a space ('my<zero-width>snap is ...'): check that reading too
        views.append(normalize("".join(" " if (unicodedata.category(c) == "Cf" or c in _BLANKS) else c for c in raw)))
    if any(_contact_view(v) for v in views):
        return "contact_info"
    return None


def scan(text: str) -> str | None:
    if len(text or "") > MAX_SCAN_CHARS:
        return "too_long"
    return scan_language(text) or scan_contact(text) or scan_grooming(text)


def check(text: str, context: str = "") -> str:
    """Return the cleaned text, or raise ChatBlocked(422) with the user-facing message. Nothing is stored/sent on a block."""
    text = (text or "").strip()
    r = scan(text)
    if r == "too_long":
        raise ChatBlocked(413, {"code": "too_long", "message": "That text is too long. Please make it shorter.", "context": context})
    if r == "unavailable":
        raise ChatBlocked(503, {"code": "filter_unavailable", "message": UNAVAILABLE_MESSAGE, "context": context})
    if r:
        msg = BLOCK_MESSAGE if r == "language" else CONTACT_MESSAGE
        raise ChatBlocked(422, {"code": "language_blocked" if r == "language" else "contact_blocked",
                                "message": msg, "context": context})
    return text


def gate(actor: Actor, text: str, context: str) -> str:
    """Single entry point for every free-text field other people can read (feedback, titles, descriptions, nicknames…)."""
    return check(text, context)


def filter_only(text: str, what: str) -> str:
    """Same gate; raises ChatBlocked (one error shape everywhere: the app answers 422/413/503 with code, message, context and detail)."""
    return check(text, what)
