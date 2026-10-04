#!/usr/bin/env python3
"""Red-team harness for ZEIM's language/PII filter (app/community/safety.py). READ-ONLY: imports the module, never edits app code,
never touches live data (no server involved).

Run:  PYTHONPATH=/workspace/photo3d /workspace/photo3d/.venv/bin/python /workspace/photo3d/reports/filter_redteam.py
Optional: /tmp/rt_corpus_<lang>.txt (one word per line; made with `wordfreq` in /tmp/rtvenv) enables the dictionary false-positive sweep.
Output:   reports/filter-redteam-results.json (abusive terms are MASKED, e.g. f***), plus a console summary.

Abusive test inputs are generated from the app's own word lists at runtime; this file contains no slurs. The few hand-written
non-English profanity probes are stored as \\u escapes and always masked in output.
"""
# NOTE: single 50k-char and 100k-char words were measured once by hand: 43.9 s and 174.6 s (see report); the default run uses smaller sizes.
import json, re, sys, time, unicodedata, random
from pathlib import Path
from app.community import safety as S

OUT = Path(__file__).with_name("filter-redteam-results.json")
L = S._L.load()
random.seed(7)

def mask(w):
    return " ".join(x[0] + "*" * (len(x) - 1) if len(x) > 1 else x for x in w.split(" "))

def lang(t): return S.scan_language(t) == "language"
def contact(t): return S.scan_contact(t) == "contact_info"
def anyblock(t): return S.scan(t) is not None

RESULTS = {"fixed": [], "generated": [], "sweeps": {}}

# ------------------------------------------------------------------ word source
def lines_of(name):
    return list(L._lines(S.WL / f"{name}.txt"))
ascii_single = lambda w: re.fullmatch(r"[a-z]{4,}", w) is not None
src_words = {}
for name in ("en", "extra"):
    src_words[name] = [w for w in lines_of(name) if ascii_single(w) and w not in L.allow_words]
all_src = sorted(set(src_words["en"]) | set(src_words["extra"]))
is_stem = lambda w: any(s in w for s in L.stems)
stem_words = [w for w in all_src if is_stem(w)]
nonstem_words = [w for w in all_src if not is_stem(w)]
# only words the baseline detects (so we measure the evasion, not a list gap)
base_ok = [w for w in all_src if lang(w)]
RESULTS["sweeps"]["_source"] = {"ascii_single_words": len(all_src), "baseline_detected": len(base_ok),
                                "with_stem": len([w for w in base_ok if is_stem(w)]), "without_stem": len([w for w in base_ok if not is_stem(w)])}

# ------------------------------------------------------------------ transforms
CYR = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "y": "у", "i": "і", "s": "ѕ", "j": "ј", "h": "һ", "k": "к", "m": "м", "t": "т", "b": "в"}
GRK = {"a": "α", "o": "ο", "i": "ι", "v": "ν", "u": "υ", "p": "ρ", "k": "κ", "t": "τ", "e": "ε", "n": "η", "x": "χ", "y": "γ"}
SMALLCAP = dict(zip("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"))
LATIN_EXT = {"l": "ł", "o": "ø", "d": "đ", "i": "ı", "h": "ħ", "t": "ŧ", "b": "ƀ", "g": "ǥ", "a": "ɑ", "e": "ɘ", "s": "ſ"}
def mapall(w, m): return "".join(m.get(c, c) for c in w)
def mapone(w, m):
    for i, c in enumerate(w):
        if c in m: return w[:i] + m[c] + w[i + 1:]
    return w
def ins_mid(w, ch): k = len(w) // 2; return w[:k] + ch + w[k:]
def ins_all(w, ch): return ch.join(w)
def shift(w, base): return "".join(chr(base + ord(c) - 97) for c in w)
LEET_FULL = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "b": "8", "g": "9"}
LEET_SYM = {"a": "@", "i": "!", "s": "$", "t": "+", "o": "0", "e": "3"}
LEET_ALT = {"c": "(", "k": "|<", "u": "v", "f": "ph", "i": "|", "l": "|", "h": "#", "n": "|\\|", "w": "vv", "m": "|\\/|", "d": "|)", "p": "|>", "s": "z", "a": "/\\", "o": "()"}
def drop_vowels(w): return re.sub(r"[aeiou]", "", w[1:]) and w[0] + re.sub(r"[aeiou]", "", w[1:])
def repl_first_vowel(w, ch): return re.sub(r"[aeiou]", ch, w, count=1)
def stretch_vowels(w): return re.sub(r"([aeiou])", r"\1\1\1", w)

TRANSFORMS = {
 # spacing / punctuation
 "spaced letters (x y z)":           lambda w: " ".join(w),
 "dotted letters (x.y.z)":           lambda w: ".".join(w),
 "dashed letters (x-y-z)":           lambda w: "-".join(w),
 "underscore letters (x_y_z)":       lambda w: "_".join(w),
 "comma letters (x,y,z)":            lambda w: ",".join(w),
 "slash letters (x/y/z)":            lambda w: "/".join(w),
 "asterisk letters (x*y*z)":         lambda w: "*".join(w),
 "mid split with space (xy z)":      lambda w: ins_mid(w, " "),
 "mid split with dot (xy.z)":        lambda w: ins_mid(w, "."),
 "mid split with hyphen (xy-z)":     lambda w: ins_mid(w, "-"),
 "mid split with asterisk (xy*z)":   lambda w: ins_mid(w, "*"),
 "mid split with underscore (xy_z)": lambda w: ins_mid(w, "_"),
 "mid split with slash (xy/z)":      lambda w: ins_mid(w, "/"),
 "mid split with emoji (xy🔥z)":      lambda w: ins_mid(w, "🔥"),
 "every letter + emoji":             lambda w: ins_all(w, "😀"),
 "vowel -> * (f*ck style)":          lambda w: repl_first_vowel(w, "*"),
 "vowel -> # ":                      lambda w: repl_first_vowel(w, "#"),
 "vowel -> _ ":                      lambda w: repl_first_vowel(w, "_"),
 "vowels dropped (fck style)":       drop_vowels,
 "reversed":                         lambda w: w[::-1],
 # leet
 "leet digits (all)":                lambda w: mapall(w, LEET_FULL),
 "leet symbols (@ ! $ +)":           lambda w: mapall(w, LEET_SYM),
 "leet 1 first replaceable":         lambda w: mapone(w, LEET_FULL),
 "leet ascii-art (( |< ph vv |)":    lambda w: mapall(w, LEET_ALT),
 "leet ascii-art single char":       lambda w: mapone(w, LEET_ALT),
 # stretching
 "stretch every letter x2":          lambda w: "".join(c * 2 for c in w),
 "stretch vowels x3":                stretch_vowels,
 "stretch last letter x4":           lambda w: w + w[-1] * 3,
 "stretch first letter x4":          lambda w: w[0] * 3 + w,
 "double one mid letter (xyyz)":     lambda w: w[:len(w)//2] + w[len(w)//2] + w[len(w)//2:],
 # homoglyphs
 "Cyrillic lookalikes (all)":        lambda w: mapall(w, CYR),
 "Cyrillic lookalike (1 char)":      lambda w: mapone(w, CYR),
 "Greek lookalikes (all)":           lambda w: mapall(w, GRK),
 "Greek lookalike (1 char)":         lambda w: mapone(w, GRK),
 "small-caps letters":               lambda w: mapall(w, SMALLCAP),
 "Latin-ext lookalikes (ł ø đ ı)":  lambda w: mapall(w, LATIN_EXT),
 # invisible / combining
 "zero-width space mid (U+200B)":    lambda w: ins_mid(w, "\u200b"),
 "zero-width space every letter":    lambda w: ins_all(w, "\u200b"),
 "zero-width joiner mid (U+200D)":   lambda w: ins_mid(w, "\u200d"),
 "zero-width non-joiner mid":        lambda w: ins_mid(w, "\u200c"),
 "soft hyphen mid (U+00AD)":         lambda w: ins_mid(w, "\u00ad"),
 "word joiner mid (U+2060)":         lambda w: ins_mid(w, "\u2060"),
 "BOM / ZWNBSP mid (U+FEFF)":        lambda w: ins_mid(w, "\ufeff"),
 "LRM/RLM mid (U+200E)":             lambda w: ins_mid(w, "\u200e"),
 "bidi override wrap (U+202E)":      lambda w: "\u202e" + w + "\u202c",
 "variation selector mid (U+FE0F)":  lambda w: ins_mid(w, "\ufe0f"),
 "Mongolian VS mid (U+180B)":        lambda w: ins_mid(w, "\u180b"),
 "tag char mid (U+E0041)":           lambda w: ins_mid(w, "\U000e0041"),
 "invisible separator mid (U+2063)": lambda w: ins_mid(w, "\u2063"),
 "Hangul filler mid (U+3164)":       lambda w: ins_mid(w, "\u3164"),
 "combining acute on every letter":  lambda w: "".join(c + "\u0301" for c in w),
 "zalgo (3 marks per letter)":       lambda w: "".join(c + "\u0300\u0316\u035b" for c in w),
 "enclosing circle U+20DD mid":      lambda w: ins_mid(w, "\u20dd"),
 "combining grapheme joiner mid":    lambda w: ins_mid(w, "\u034f"),
 "NBSP between letters":             lambda w: "\u00a0".join(w),
 "ideographic space between letters":lambda w: "\u3000".join(w),
 # alternative alphabets that NFKD should/shouldn't fold
 "fullwidth Latin":                  lambda w: "".join(chr(ord(c) + 0xFEE0) for c in w),
 "math bold":                        lambda w: shift(w, 0x1D41A),
 "math double-struck":               lambda w: shift(w, 0x1D552),
 "circled letters":                  lambda w: shift(w, 0x24D0),
 "parenthesized letters":            lambda w: shift(w, 0x249C),
 "squared letters":                  lambda w: shift(w, 0x1F130),
 "negative squared letters":         lambda w: shift(w, 0x1F170),
 "regional-indicator letters":       lambda w: shift(w, 0x1F1E6),
 "negative circled letters":         lambda w: shift(w, 0x1F150),
 # glue / context
 "prefix glue (superXYZ)":           lambda w: "super" + w,
 "suffix glue (XYZhead)":            lambda w: w + "head",
 "suffix glue (XYZface)":            lambda w: w + "face",
 "digits glued (XYZ123)":            lambda w: w + "123",
 "double-wrapped (xxXYZxx)":         lambda w: "xx" + w + "xx",
 "CamelCase compound":               lambda w: "Big" + w.capitalize() + "Guy",
 "hyphen-glued to word (big-XYZ)":   lambda w: "big-" + w,
 "repeated ('XYZ XYZ' baseline)":    lambda w: w + " " + w,
 "uppercase":                        lambda w: w.upper(),
 "alternating case":                lambda w: "".join(c.upper() if i % 2 else c for i, c in enumerate(w)),
 "plural (-s)":                      lambda w: w + "s",
 "-ing":                             lambda w: w + "ing",
 "-ed":                              lambda w: w + "ed",
 "-er":                              lambda w: w + "er",
 "-y":                               lambda w: w + "y",
 "-ness":                            lambda w: w + "ness",
 "-ish":                             lambda w: w + "ish",
 "-ly":                              lambda w: w + "ly",
 "in sentence ('you are a XYZ')":    lambda w: "you are a " + w,
}

def sweep(name, fn, words):
    hit = miss = 0; ex_miss = []
    for w in words:
        t = fn(w)
        if lang(t): hit += 1
        else:
            miss += 1
            if len(ex_miss) < 3: ex_miss.append(mask(w))
    return {"n": hit + miss, "blocked": hit, "missed": miss, "block_rate": round(hit / max(1, hit + miss), 3), "missed_examples_masked": ex_miss}

print("== A. generated evasion sweeps (words from en.txt/extra.txt, baseline-detected only) ==")
sw = {}
for name, fn in TRANSFORMS.items():
    a = sweep(name, fn, [w for w in base_ok if is_stem(w)]) if False else None
    all_r = sweep(name, fn, base_ok)
    st = sweep(name, fn, [w for w in base_ok if is_stem(w)])
    ns = sweep(name, fn, [w for w in base_ok if not is_stem(w)])
    sw[name] = {"all": all_r, "stem_words": st, "non_stem_words": ns}
    print(f"{name:42s} all {all_r['block_rate']:.2f} ({all_r['blocked']}/{all_r['n']})  stem {st['block_rate']:.2f}  nonstem {ns['block_rate']:.2f}")
RESULTS["sweeps"]["transforms"] = sw

# ---- phrases from lists
print("\n== B. multi-word phrases from the lists ==")
phr = sorted({" ".join(p) for p in L.phrases if all(re.fullmatch(r"[a-z]+", t) for t in p)})
phr_ok = [p for p in phr if lang(p)]
pv = {
 "baseline": lambda p: p, "glued (no spaces)": lambda p: p.replace(" ", ""),
 "hyphenated": lambda p: p.replace(" ", "-"), "underscored": lambda p: p.replace(" ", "_"),
 "dots instead of spaces": lambda p: p.replace(" ", "."), "leet digits": lambda p: mapall(p, LEET_FULL),
 "Cyrillic lookalikes": lambda p: mapall(p, CYR), "ZWSP in each word": lambda p: " ".join(ins_mid(x, "\u200b") for x in p.split()),
 "doubled letters": lambda p: " ".join("".join(c * 2 for c in x) for x in p.split()), "each word spaced out": lambda p: "  ".join(" ".join(x) for x in p.split()),
 "word order swapped (last first)": lambda p: " ".join(reversed(p.split())),
 "extra filler word between": lambda p: " really ".join(p.split(" ", 1)) if " " in p else p,
 "contraction/slang dropped vowels": lambda p: " ".join(drop_vowels(x) if len(x) > 3 else x for x in p.split()),
}
phr_res = {}
for n, fn in pv.items():
    r = sweep(n, fn, phr_ok); phr_res[n] = r
    print(f"{n:36s} {r['block_rate']:.2f} ({r['blocked']}/{r['n']})")
RESULTS["sweeps"]["phrases"] = {"total_listed_phrases": len(phr), "baseline_detected": len(phr_ok), "variants": phr_res,
                                "baseline_not_detected_masked": [mask(p) for p in phr if p not in phr_ok][:40]}

# ---- list integrity: does every entry of every list trigger?
print("\n== C. list integrity / per-language baseline ==")
integ = {}
for f in sorted(S.WL.glob("*.txt")):
    if f.name in ("allow_words.txt", "allow_phrases.txt", "stems.txt") or f.name.startswith("LICENSE"): continue
    name = f.stem; ents = list(L._lines(f)); miss_short = miss_allow = miss_other = 0; other_ex = []
    for e in ents:
        if lang(e): continue
        toks = re.findall(r"\w+", e)
        if name not in ("en", "extra") and len(e) <= 3: miss_short += 1
        elif len(toks) == 1 and toks[0] in L.allow_words: miss_allow += 1
        else:
            miss_other += 1
            if len(other_ex) < 5: other_ex.append(mask(e))
    integ[name] = {"entries": len(ents), "not_blocked_short_foreign": miss_short, "not_blocked_allowlisted": miss_allow, "not_blocked_other": miss_other, "other_examples_masked": other_ex}
    print(f"{name:6s} entries={len(ents):4d} short-ignored={miss_short:3d} allowlisted={miss_allow:3d} other={miss_other:3d} {other_ex}")
RESULTS["sweeps"]["list_integrity"] = integ

# ---- licence-file contamination: safety._Lists.load() globs *.txt, so LICENSE-CC-BY-4.0.txt is loaded as a word list
lic = list(L._lines(S.WL / "LICENSE-CC-BY-4.0.txt"))
lic_words = sorted({re.findall(r"\w+", l)[0] for l in lic if len(re.findall(r"\w+", l)) == 1})
lic_phr = [l for l in lic if len(re.findall(r"\w+", l)) > 1]
common = ["work", "works", "license", "licensor", "material", "rights", "right", "terms", "rules", "public", "effect", "section", "notice", "party", "following", "effective", "copyright", "creative", "commons", "attribution", "adapted", "limited", "waiver", "reproduce", "share", "database", "moral", "patent", "trademark", "warranties", "liability", "disclaimer", "termination", "exercise", "sublicense", "format", "technical", "modification", "automatically", "reasonable", "means", "exclusive", "unless", "otherwise", "provided", "required"]
hit_common = [w for w in common if lang(w)]
lic_hit_phr = []
for l in lic_phr[:400]:
    t = " ".join(re.findall(r"\w+", l)[:3])
    if len(t.split()) >= 2 and lang(t): lic_hit_phr.append(t)
RESULTS["sweeps"]["license_file_loaded_as_list"] = {"loaded_file": "LICENSE-CC-BY-4.0.txt", "single_word_entries_added": len(lic_words), "multi_word_entries_added": len(lic_phr),
    "ordinary_words_now_blocked": hit_common, "sample_blocked_phrases_3word_prefix": lic_hit_phr[:15]}
print("\n== C2. licence file loaded as a word list ==")
print("single-word entries added:", len(lic_words), " phrases added:", len(lic_phr))
print("ordinary words now blocked:", hit_common)
print("phrase samples:", lic_hit_phr[:15])

# ---- other-language transforms (derived programmatically from the lists)
print("\n== D. other-language evasions (derived from the lists) ==")
CYR2LAT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a","b","v","g","d","e","e","zh","z","i","i","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","shch","","y","","e","yu","ya"]))
RU_LOOK = {"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "к": "k", "м": "m", "т": "t", "в": "b", "н": "h"}
ru = [w for w in lines_of("ru") if re.fullmatch(r"[а-яё]{4,}", w)]
ru_ok = [w for w in ru if lang(w)]
lang_sweeps = {}
def rsweep(name, fn, ws): lang_sweeps[name] = sweep(name, fn, ws); r = lang_sweeps[name]; print(f"{name:52s} {r['block_rate']:.2f} ({r['blocked']}/{r['n']})")
rsweep("ru: baseline Cyrillic", lambda w: w, ru_ok)
rsweep("ru: Latin transliteration", lambda w: "".join(CYR2LAT.get(c, c) for c in w), ru_ok)
rsweep("ru: Cyrillic written w/ Latin lookalikes", lambda w: "".join(RU_LOOK.get(c, c) for c in w), ru_ok)
rsweep("ru: spaced letters", lambda w: " ".join(w), ru_ok)
rsweep("ru: stretched (x3 vowels)", lambda w: re.sub(r"([аеиоуыэюя])", r"\1\1\1", w), ru_ok)
rsweep("ru: ZWSP mid", lambda w: ins_mid(w, "\u200b"), ru_ok)
rsweep("ru: dotted letters", lambda w: ".".join(w), ru_ok)
de = [w for w in lines_of("de") if re.fullmatch(r"[a-zäöüß]{4,}", w) and re.search("[äöüß]", w) or False]
de_all = [w for w in lines_of("de") if re.fullmatch(r"[a-zäöüß]{4,}", w)]
GE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
# note: list entries are NFKD-stripped by the app, so 'ä' -> 'a' ; the user typing 'ae' is the realistic bypass
de_um = [w for w in de_all if re.search("[äöüß]", w) and lang(w)]
rsweep("de: umlaut words typed ASCII-style (ae/oe/ue/ss)", lambda w: "".join(GE.get(c, c) for c in w), de_um)
for code in ("es", "fr", "de", "it", "pt", "nl", "tr", "pl"):
    ws = [w for w in lines_of(code) if re.fullmatch(r"[a-zà-ÿñçßœ]{4,}", w) and lang(w)]
    rsweep(f"{code}: leet digits", lambda w: mapall(w, LEET_FULL), ws)
    rsweep(f"{code}: spaced letters", lambda w: " ".join(w), ws)
    rsweep(f"{code}: Cyrillic lookalikes", lambda w: mapall(w, CYR), ws)
    rsweep(f"{code}: ZWSP mid", lambda w: ins_mid(w, "\u200b"), ws)
    rsweep(f"{code}: suffix glue (+head)", lambda w: w + "head", ws)
    rsweep(f"{code}: in sentence w/ Spanish/French inflection (-s/-es)", lambda w: w + "es", ws)
RESULTS["sweeps"]["other_languages"] = lang_sweeps

# ---- Unlisted languages: hand-written probes (stored as escapes; masked in output)
PROBES = {
 "Japanese (common profanity, kana)": "\u304f\u305d",
 "Japanese (kill-yourself, kanji)": "\u6b7b\u306d",
 "Chinese (profanity, hanzi)": "\u4ed6\u5988\u7684",
 "Chinese (vulgar insult, hanzi)": "\u50bb\u903c",
 "Korean (profanity, hangul)": "\uc528\ubc1c",
 "Greek (insult)": "\u03bc\u03b1\u03bb\u03ac\u03ba\u03b1",
 "Arabic (insult)": "\u0627\u0628\u0646 \u0627\u0644\u0643\u0644\u0628",
 "Hindi (vulgar insult)": "\u091a\u0942\u0924\u093f\u092f\u093e",
 "Vietnamese (profanity)": "\u0111\u1ee5 m\u00e1",
 "Indonesian (insult)": "bangsat",
 "Tagalog (profanity)": "putang ina",
 "Romaji Japanese (profanity)": "kuso",
 "Romaji Japanese (shine = die)": "shine",
}
probe_res = []
for k, v in PROBES.items():
    r = lang(v); probe_res.append({"class": k, "masked": mask(v) if v.isascii() else v[0] + "*" * (len(v) - 1), "blocked": r})
    print(f"{k:40s} blocked={r}")
RESULTS["sweeps"]["unlisted_language_probes"] = probe_res

# ------------------------------------------------------------------ dictionary false-positive sweep
print("\n== E. dictionary false-positive sweep ==")
corp = {}
for code in ("en", "es", "fr", "de"):
    p = Path(f"/tmp/rt_corpus_{code}.txt")
    if p.exists():
        words = [w for w in p.read_text(encoding="utf-8").split() if w.isalpha()]
        flagged = [w for w in words if lang(w)]
        BENIGN_HINT = set("hard harder hardy harding information informations rights conditions agreements material materials materially license licenses licensees licensor warranties designated finger fingers gotten stake stakes peter peters nigeria nigerian nigerians niger moses spicy spices spiced pitt frances franc francs anita regina pippa scatter inferno gerber butters cummings shenanigans minigames comer comers pele pina pica rosette escorted nicht bitte weniger gottes dritter martillo balle balles reiniger".split())
        corp[code] = {"words_tested": len(words), "flagged": len(flagged),
                      "flagged_benign_looking": [w for w in flagged if w in BENIGN_HINT],
                      "flagged_other_masked": [mask(w) for w in flagged if w not in BENIGN_HINT]}
        print(code, len(words), "flagged", len(flagged))
RESULTS["sweeps"]["dictionary"] = corp

# ------------------------------------------------------------------ fixed cases
def T(cat, cls, text, expect, check, sens=False, note=""):
    """expect: 'block' or 'pass'. check: which scanner(s) count. sens=True -> mask text in outputs."""
    got = check(text)
    ok = (got if expect == "block" else (not got))
    RESULTS["fixed"].append({"cat": cat, "class": cls, "input": mask(text) if sens else text, "expect": expect, "actual": "blocked" if got else "allowed", "ok": ok, "note": note})

# ---- False positives (benign, expect pass on the full gate)
FP = [
 # maker / 3D printing
 "Print bed adhesion tips", "My nozzle is clogged", "Set infill to 20 percent", "Cockpit canopy for my plane model", "Bed leveling and first layer",
 "Retraction and stringing settings", "Support structures and overhangs", "Raft vs brim", "Hot end temperature 210C", "Cooling fan duct for the hotend",
 "Extruder gear and idler", "Layer height 0.2 mm", "Belt tensioner for the Y axis", "Linear rail and lead screw", "Stepper motor mount NEMA17",
 "Print speed jerk and acceleration", "Klipper jerk settings", "Butt joint vs lap joint", "Butt weld style seam", "Nipple fitting for pneumatic tube",
 "Master and slave cylinder", "Thrust bearing holder", "Male and female connector", "Dovetail joint", "Knob for the printer control",
 "Cable tie and tight fit tolerance", "Hard stop for the limit switch", "Screw hole and bolt pattern", "Nut and bolt organiser", "Threaded rod coupler",
 "Rubber feet for the bed", "Spool holder for PLA", "Glass bed with PEI sheet", "Brass nozzle 0.4", "Hardened steel nozzle", "Bowden tube clip", "Snap fit lid", "Snap-fit enclosure",
 "Snap together puzzle", "Click and snap lock", "Print in place hinge", "Pin and socket joint", "Peg board hooks", "Shaft collar", "Pulley and idler",
 "Chicken breast cookie cutter", "Breast cancer awareness ribbon", "Rooster weathervane", "Cock robin bird feeder", "Woodpecker bird house", "Peacock feather lamp",
 "Blue tit nest box", "Raccoon planter", "Dike and levee model", "Bastard file holder", "Spic and span cleaning caddy", "Gas pipe cap", "Shiitake mushroom stamp",
 "Hancock bridge model", "Scunthorpe railway station", "Penistone viaduct", "Middlesex county map", "Sussex cathedral", "Essex lighthouse", "Cockermouth castle",
 "Assassin's Creed helmet", "Assembly instructions", "Assess your print quality", "Class project: bridge", "Classroom organiser", "Compass holder", "Bass guitar stand",
 "Grass planter", "Mass of the object 150 g", "Analysis of failed prints", "Cucumber slicer", "Document holder", "Therapist office sign", "Pass the filament please",
 "Embassy gate model", "Harass is not allowed", "Passion project", "Arsenal FC badge", "Butterfly keychain", "Button cell holder", "Hitchcock film reel", "Dickens quote stand",
 "Titanic ship model", "Sextant model", "Sextuple pack organiser", "Cumbria map", "Matsushita robot", "Shitennoji temple model", "Bangkok skyline", "Wankel engine model",
 "Pennsylvania state keychain", "Lake Titicaca map", "Fukushima map", "Fukuoka tower", "Nagasaki dome", "Kanazawa castle", "Tsukuba science city",
 "Cumberland sausage stand", "Cummings desk sign", "Sexton house sign", "Hoare Street sign", "Blowfish pencil holder", "Blow molding explained", "Shooting star ornament",
 "Shoot the moon", "Kill switch for the printer", "Kill the process and restart the slicer", "Dead pixel tester", "Execute the gcode", "Abort print", "Hang the ornament",
 "Hole punch and cut", "Hell yeah, it worked!", "Damn, the print failed", "What the heck", "Crap, I ran out of filament", "Bloody brilliant benchy",
 "I'm gay and proud, rainbow flag stand", "My friend is gay", "Lesbian flag keychain", "Transgender pride flag stand", "Jewish menorah model", "Muslim prayer beads", "Black history month sign",
 "Asian food stand", "Mexican hat planter", "Indian elephant statue", "White rabbit figurine", "Gypsy moth model", "Chinese dragon", "Polish pottery stand", "Turkish delight box",
 "Nazi Germany history project", "Holocaust memorial model", "World War II tank", "Slave trade history", "Civil rights march", "Abortion debate", "Drug awareness project", "Suicide prevention hotline sign",
 "Shot glass holder", "Whiskey barrel planter", "Beer mug", "Wine rack", "Cigarette holder", "Weed whacker bracket", "Pot holder", "Crack in the print", "Bone china", "Boner", "Bondage tape", "Rim of the wheel",
 "Dyke Road", "Fanny pack clip", "Randy Pausch", "Dick Van Dyke", "Richard", "Moby Dick", "Peter Piper", "Willy Wonka", "Wang Wei", "Kim Fuk", "Hunter Bates", "Lipschitz constant", "Gaylord Texas",
 "Anne Hoare", "Michael Cox", "Ben Dover", "Mike Rotch", "Seymour Butts", "Jackson Pollock", "Matt Cockburn", "Fucik", "Brandon Cummings", "Kuntz family", "Niggle", "Niggardly", "Snigger",
 "Fart-proof lid", "Poop emoji bin", "Pee cup holder", "Toilet paper holder", "Booger", "Butt cheek", "Underpants", "Sexy beast statue", "Sex education class", "Sexual education project",
 "Puberty education", "Breast pump bracket", "Condom dispenser sign", "Penis" , "Vagina", "Reproductive system model", "Anatomy lesson: heart and lungs",
 "Ball bearing holder", "Ball joint", "Balls of filament", "Golf balls rack", "Nuts and bolts", "Hard core filament", "Naked eye astronomy", "Naked mole rat",
 "Gift box", "Kind regards", "Rock climbing wall", "Hose clamp", "Fart", "Puta madre", "Pipi", "Caca de vaca", "Sexo", "Coger la pelota", "Pene", "Verga", "Chinga",
 "Fick", "Mist", "Gift", "Arsch", "Kot", "Schwul", "Bad", "Sein", "Kind", "Hoch", "Con", "Merde alors", "Pute", "Bite", "Con amor",
 # numbers / dates / measurements
 "Print time 12:30 on 2026-10-04 12:45", "Printed 1234567890 layers", "Version 1.2.3.4.5.6.7", "Temps 200 210 220 230 240", "Weighs 1,234,567 grams", "Model has 1.4 M triangles",
 "Size 150 x 150 x 150 mm", "0.2 0.2 0.2 0.2 0.2 0.2 0.2", "Order 66", "Room 101", "Grade 5 class 3B", "Year 2026 week 40 day 4 hour 16", "Coordinates 41.8781 -87.6298", "G-code: G1 X10.5 Y20.25 Z0.2 F1500",
 "Pi is 3.14159265358979", "1 2 3 4 5 6 7 8 9 10 steps", "Serial no 12 34 56 78 90", "Budget $1,000,000", "Weight 12345 67890", "Price 19.99 29.99 39.99 49.99",
 # sentences with "." joins/typos that look like domains
 "I like it.Me too", "Great print.Dev", "Done.Me and my brother printed it", "Version 2.io", "The result is good.App works", "He said hello.Org chart attached", "Look at this.Tv stand", "Ok.Gg wp",
 "I love snapchat filters", "I love Instagram reels", "Discord is fun", "My brother uses TikTok videos", "Telegram was invented in 1844", "WhatsApp is popular", "Kik is a game", "Insta ready photo", "Snap fit joints are strong",
 "Snap the two halves together", "snap off the support", "Snapchat vs Instagram essay", "Discord bot project for class", "Instagram post about my print",
 "Email me later is not allowed", "The at symbol", "Dot com bubble history", "Meet at noon", "Please text me in class", "Call of Duty fan art", "Phone stand", "Phone case", "Email icon", "Mail box", "Contact sheet",
 "Gmail icon keychain", "Links in a chain", "Chain link fence", "Hyperlink icon", "Website tips", "Name tag", "My address book holder", "Home sweet home sign", "Street sign model", "Main Street USA diorama",
 "Oak Street", "I live in Texas", "My school is great", "I am 12 years old", "I'm in 6th grade", "I'm ten and I love Minecraft",
]
for t in FP: T("False positive", "benign phrase", t, "pass", anyblock)

# ---- evasions in context (fixed, hand-built from list words at runtime)
sample_stem = next(w for w in sorted(stem_words) if lang(w) and len(w) == 4)
sample_nonstem = next(w for w in sorted(nonstem_words) if lang(w) and len(w) in (4, 5) and not any(ch in w for ch in "ouyae") is False)
print("\n(fixed-case samples used:", mask(sample_stem), mask(sample_nonstem), ")")

# ---- PII: contact detection
PII = [
 # emails
 ("email", "plain email", "mail me at john.smith@gmail.com", "block"),
 ("email", "'name at gmail dot com'", "email me john smith at gmail dot com", "block"),
 ("email", "'name AT gmail DOT com'", "johnsmith AT gmail DOT com", "block"),
 ("email", "name (at) gmail (dot) com", "johnsmith (at) gmail (dot) com", "block"),
 ("email", "name [at] gmail [dot] com", "johnsmith [at] gmail [dot] com", "block"),
 ("email", "name{at}gmail{dot}com", "johnsmith{at}gmail{dot}com", "block"),
 ("email", "name <at> gmail <dot> com", "johnsmith <at> gmail <dot> com", "block"),
 ("email", "'name @ gmail . com' spaced", "johnsmith @ gmail . com", "block"),
 ("email", "name @gmail (no TLD)", "johnsmith@gmail", "block"),
 ("email", "fullwidth @ symbol", "johnsmith\uff20gmail.com", "block"),
 ("email", "small-commercial-at U+FE6B", "johnsmith\ufe6bgmail.com", "block"),
 ("email", "ZWSP inside address", "johnsmith@gm\u200bail.com", "block"),
 ("email", "ZWSP inside domain+TLD", "johnsmith@gmail.c\u200bom", "block"),
 ("email", "'name at gmail' no dot", "my email is johnsmith at gmail", "block"),
 ("email", "'gmail: name'", "gmail: johnsmith2012", "block"),
 ("email", "spelled domain 'g mail'", "johnsmith at g mail dot com", "block"),
 ("email", "'dot' only", "johnsmith@gmail dot com", "block"),
 ("email", "'at' only with real dot", "johnsmith at gmail.com", "block"),
 ("email", "name+tag@sub.domain.co.uk", "a+b@mail.school.co.uk", "block"),
 ("email", "unicode IDN domain", "kid@пример.рф", "block"),
 ("email", "obfuscated 'name-at-domain-dot-tld'", "johnsmith-at-gmail-dot-com", "block"),
 ("email", "uppercase/mixed", "JohnSmith@GMAIL.COM", "block"),
 ("email", "'shift-2' hint", "johnsmith shift 2 gmail dot com", "block"),
 ("email", "hotmail/outlook/yahoo word only", "my hotmail is coolkid_99", "block"),
 ("email", "'at' in reverse language (arroba)", "johnsmith arroba gmail punto com", "block"),
 ("email", "'chez' style FR", "johnsmith arobase gmail point com", "block"),
 # phone
 ("phone", "US 10-digit dashes", "call 555-123-4567", "block"),
 ("phone", "US 10-digit plain", "call 5551234567", "block"),
 ("phone", "(555) 123-4567", "call (555) 123-4567", "block"),
 ("phone", "+1 country code", "call +1 555 123 4567", "block"),
 ("phone", "7-digit local number", "call 555-1234", "block"),
 ("phone", "7-digit local number plain", "my number is 5551234", "block"),
 ("phone", "dotted 555.123.4567", "555.123.4567", "block"),
 ("phone", "comma separated digits", "555,123,4567", "block"),
 ("phone", "slash separated digits", "555/123/4567", "block"),
 ("phone", "underscore separated digits", "555_123_4567", "block"),
 ("phone", "middle-dot separated", "555\u00b7123\u00b74567", "block"),
 ("phone", "digits split by letters", "5a5a5a1a2a3a4a5a6a7", "block"),
 ("phone", "digits split by emoji", "5\U0001F525" "5\U0001F525" "5\U0001F525" "1\U0001F525" "2\U0001F525" "3\U0001F525" "4\U0001F525" "5\U0001F525" "6\U0001F525" "7", "block"),
 ("phone", "spelled-out digits (words)", "five five five one two three four five six seven", "block"),
 ("phone", "spelled-out with dashes", "five-five-five-one-two-three-four-five-six-seven", "block"),
 ("phone", "spelled-out uppercase", "FIVE FIVE FIVE ONE TWO THREE FOUR FIVE SIX SEVEN", "block"),
 ("phone", "mixed digits and words", "5 5 5 one two three 4 5 6 7", "block"),
 ("phone", "spelled with 'oh' for zero", "five oh five one two three four five six seven", "block"),
 ("phone", "spelled with 'double'/'triple'", "triple five one two three four five six seven", "block"),
 ("phone", "spelled out Spanish", "cinco cinco cinco uno dos tres cuatro cinco seis siete", "block"),
 ("phone", "spelled out German", "fünf fünf fünf eins zwei drei vier fünf sechs sieben", "block"),
 ("phone", "spelled out French", "cinq cinq cinq un deux trois quatre cinq six sept", "block"),
 ("phone", "fullwidth digits", "\uff15\uff15\uff15\uff11\uff12\uff13\uff14\uff15\uff16\uff17", "block"),
 ("phone", "Arabic-Indic digits", "\u0665\u0665\u0665\u0661\u0662\u0663\u0664\u0665\u0666\u0667", "block"),
 ("phone", "keycap emoji digits", "5\ufe0f\u20e3" "5\ufe0f\u20e3" "5\ufe0f\u20e3" "1\ufe0f\u20e3" "2\ufe0f\u20e3" "3\ufe0f\u20e3" "4\ufe0f\u20e3" "5\ufe0f\u20e3" "6\ufe0f\u20e3" "7\ufe0f\u20e3", "block"),
 ("phone", "math-bold digits", "".join(chr(0x1D7CE + int(c)) for c in "5551234567"), "block"),
 ("phone", "digits split across 2 messages-style (first half)", "my number starts with 555 123", "block"),
 ("phone", "leet-letter digits (S=5 O=0)", "S5S l23 4S67", "block"),
 ("phone", "UK mobile", "07700 900123", "block"),
 ("phone", "international long", "+44 7700 900123", "block"),
 ("phone", "digits with ZWSP", "555\u200b123\u200b4567", "block"),
 ("phone", "'call me on' + 3+3+4 words+digits", "call me on 555 123 four five six seven", "block"),
 ("phone", "text 'five five five' only 3 groups", "five five five", "pass"),
 # links
 ("link", "https URL", "see https://example.com/x", "block"),
 ("link", "www prefix", "see www.example.com", "block"),
 ("link", "bare .com", "see example.com", "block"),
 ("link", "bare .net/.org", "example.net example.org", "block"),
 ("link", "bare .co.uk", "see example.co.uk", "block"),
 ("link", "bare .ru", "see example.ru", "block"),
 ("link", "bare .xyz", "see example.xyz", "block"),
 ("link", "bare .info", "see example.info", "block"),
 ("link", "bare .us/.uk/.ca/.de", "see example.de and example.uk", "block"),
 ("link", "bare .be (youtu.be)", "youtu.be/abc123", "block"),
 ("link", "bare .gl (goo.gl)", "goo.gl/abc123", "block"),
 ("link", "bare .link / .page / .site / .online", "see example.link example.site example.online", "block"),
 ("link", "bare .fm/.cc/.to/.ws/.co", "see example.cc and example.to", "block"),
 ("link", "bare .ly shortener", "bit.ly/abc", "block"),
 ("link", "discord invite", "discord.gg/abcd", "block"),
 ("link", "'dot com' spelled", "example dot com", "block"),
 ("link", "'(dot)' spelled", "example (dot) com", "block"),
 ("link", "spaced dot", "example . com", "block"),
 ("link", "dot with fullwidth period", "example\u3002com", "block"),
 ("link", "dot with fullwidth full stop U+FF0E", "example\uff0ecom", "block"),
 ("link", "hxxp defang", "hxxps://example[.]com", "block"),
 ("link", "bracketed dot", "example[.]com", "block"),
 ("link", "ZWSP before TLD", "example.\u200bcom", "block"),
 ("link", "IPv4 address", "go to 192.168.1.20:8765", "block"),
 ("link", "IPv4 w/ spaces", "192 168 1 20", "block"),
 ("link", "localhost", "localhost:8765", "block"),
 ("link", "ftp scheme", "ftp://host/file", "block"),
 ("link", "mailto scheme", "mailto:kid@example.com", "block"),
 ("link", "javascript scheme", "javascript:alert(1)", "block"),
 ("link", "data scheme", "data:text/html,hi", "block"),
 ("link", "uppercase scheme", "HTTPS://EXAMPLE.COM", "block"),
 ("link", "homoglyph in scheme", "htt\u0440s://example.com", "block"),
 ("link", "Cyrillic o in .com", "example.c\u043em", "block"),
 ("link", "'tinyurl' path only", "tinyurl com abc", "block"),
 ("link", "QR / 'search for' hint", "search for zeim on youtube channel coolkid99", "block"),
 # handles / social usernames
 ("handle", "bare @handle", "follow me @coolkid_99", "block"),
 ("handle", "@handle alone", "@coolkid_99", "block"),
 ("handle", "snap: name", "snap: coolkid99", "block"),
 ("handle", "'my snap is name'", "my snap is coolkid99", "block"),
 ("handle", "'add me on snap' w/o name", "add me on snap", "block"),
 ("handle", "'snap me'", "snap me", "block"),
 ("handle", "'snap me later'", "snap me later", "block"),
 ("handle", "'sc: name' abbreviation", "sc: coolkid99", "block"),
 ("handle", "'ig: name' abbreviation", "ig: coolkid99", "block"),
 ("handle", "'insta' with name", "insta coolkid99", "block"),
 ("handle", "'IG' @", "IG @coolkid99", "block"),
 ("handle", "discord name#1234", "discord coolkid#1234", "block"),
 ("handle", "bare name#1234", "coolkid#1234", "block"),
 ("handle", "kik name", "kik: coolkid99", "block"),
 ("handle", "whatsapp me", "whatsapp me", "block"),
 ("handle", "'dm me'", "dm me", "block"),
 ("handle", "'text me'", "text me", "block"),
 ("handle", "'pm me'", "pm me", "block"),
 ("handle", "youtube channel", "youtube: coolkid99", "block"),
 ("handle", "twitter / x handle", "twitter: coolkid99", "block"),
 ("handle", "x.com handle", "x dot com slash coolkid99", "block"),
 ("handle", "facebook name", "facebook: cool kid", "block"),
 ("handle", "fb abbreviation", "fb: coolkid99", "block"),
 ("handle", "roblox username", "roblox username coolkid99", "block"),
 ("handle", "minecraft username", "minecraft: coolkid99", "block"),
 ("handle", "steam friend code", "steam id coolkid99", "block"),
 ("handle", "twitch name", "twitch: coolkid99", "block"),
 ("handle", "reddit u/", "reddit u/coolkid99", "block"),
 ("handle", "bare u/ handle", "u/coolkid99", "block"),
 ("handle", "signal / viber / wechat / line", "wechat: coolkid99", "block"),
 ("handle", "skype", "skype: coolkid99", "block"),
 ("handle", "imessage / facetime", "facetime me at coolkid99", "block"),
 ("handle", "gamertag", "xbox gamertag coolkid99", "block"),
 ("handle", "platform split by ZWSP", "dis\u200bcord: coolkid99", "block"),
 ("handle", "platform with homoglyph", "d\u0456scord: coolkid99", "block"),
 ("handle", "platform leet", "d1scord: coolkid99", "block"),
 ("handle", "platform w/ separator > 12 chars", "my discord username is the following: coolkid99", "block"),
 ("handle", "platform with dot-separated letters", "s.n.a.p: coolkid99", "block"),
 ("handle", "snap spelled s-n-a-p", "s n a p coolkid99", "block"),
 ("handle", "bare username 'user:'", "username: coolkid99", "block"),
 # addresses
 ("address", "street address", "I live at 42 Oak Street", "block"),
 ("address", "street w/ city/state/zip", "42 Oak St, Springfield, IL 62704", "block"),
 ("address", "PO Box", "P.O. Box 1234", "block"),
 ("address", "'Ave'/'Blvd'/'Rd' abbreviations", "17 Maple Ave and 9 Elm Blvd and 3 Pine Rd", "block"),
 ("address", "ZIP only", "I'm in 62704", "block"),
 ("address", "UK postcode", "SW1A 1AA", "block"),
 ("address", "GPS coordinates", "41.8781, -87.6298", "block"),
 ("address", "school + town", "I go to Lincoln Middle School in Springfield", "block"),
 ("address", "'I live in <town>'", "I live in Springfield Illinois", "block"),
 ("address", "address spelled digits", "four two oak street", "block"),
 ("address", "what3words style", "///filled.count.soap", "block"),
 ("address", "maps link", "maps.google.com/?q=42+Oak", "block"),
 ("address", "plus code", "86HJV99C+W9", "block"),
 ("address", "full name + age", "My name is Emily Johnson and I am 11", "block"),
 ("address", "age disclosure", "I am 11 years old", "block"),
 ("address", "birthday disclosure", "my birthday is march 3 2014", "block"),
 ("address", "home alone disclosure", "I'm home alone today", "block"),
]
for cat, cls, t, exp in PII: T("PII: " + cat, cls, t, exp, anyblock)

# ---- Minor-safety patterns
MS = [
 ("age / personal question", "how old are you", "block"), ("age / personal question", "what is your age", "block"), ("age / personal question", "asl?", "block"),
 ("age / personal question", "a/s/l", "block"), ("age / personal question", "age?", "block"), ("age / personal question", "are you a boy or a girl", "block"),
 ("age / personal question", "what grade are you in", "block"), ("age / personal question", "when is your birthday", "block"), ("age / personal question", "how tall are you", "block"),
 ("age / personal question", "do you have a boyfriend", "block"), ("age / personal question", "are you single", "block"), ("age / personal question", "you seem very mature for your age", "block"),
 ("age / personal question", "hw old r u", "block"), ("age / personal question", "how.old.are.you", "block"), ("age / personal question", "how o l d are you", "block"),
 ("age / personal question", "h0w 0ld @re y0u", "block"), ("age / personal question", "h\u043ew \u043eld are y\u043eu", "block"), ("age / personal question", "how old\u200b are you", "block"),
 ("age / personal question", "cuántos años tienes", "block"), ("age / personal question", "quel âge as-tu", "block"), ("age / personal question", "wie alt bist du", "block"),
 ("location question", "where do you live", "block"), ("location question", "where are you from", "block"), ("location question", "what city are you in", "block"),
 ("location question", "what is your address", "block"), ("location question", "what school do you go to", "block"), ("location question", "which school are you at", "block"),
 ("location question", "what state do you live in", "block"), ("location question", "which town are you in", "block"), ("location question", "where r u", "block"),
 ("location question", "wh3re d0 y0u l1ve", "block"), ("location question", "where do you l\u200bive", "block"), ("location question", "where do u live", "block"),
 ("location question", "where do you live?? ", "block"), ("location question", "wherever you live, which neighborhood", "block"), ("location question", "dónde vives", "block"),
 ("location question", "où habites-tu", "block"), ("location question", "wo wohnst du", "block"), ("location question", "what's your zip code", "block"),
 ("location question", "what is your last name", "block"), ("location question", "what is your real name", "block"), ("location question", "what's your full name", "block"),
 ("move off-platform", "let's talk on discord", "block"), ("move off-platform", "move to discord", "block"), ("move off-platform", "chat with me somewhere else", "block"),
 ("move off-platform", "add me on snap", "block"), ("move off-platform", "snap me", "block"), ("move off-platform", "message me on whatsapp", "block"),
 ("move off-platform", "find me on roblox", "block"), ("move off-platform", "let's talk in private", "block"), ("move off-platform", "pm me", "block"),
 ("move off-platform", "dm me", "block"), ("move off-platform", "text me", "block"), ("move off-platform", "call me", "block"),
 ("move off-platform", "email me", "block"), ("move off-platform", "I'll give you my number", "block"), ("move off-platform", "give me your number", "block"),
 ("move off-platform", "what's your snap", "block"), ("move off-platform", "what's your insta", "block"), ("move off-platform", "do you have discord", "block"),
 ("move off-platform", "do you have snapchat", "block"), ("move off-platform", "hit me up on telegram", "block"), ("move off-platform", "i have a better app for chatting", "block"),
 ("move off-platform", "let's go private", "block"), ("move off-platform", "this chat is monitored, let's talk elsewhere", "block"), ("move off-platform", "s n a p me", "block"),
 ("move off-platform", "sn4p me", "block"), ("move off-platform", "sn\u0430p me", "block"), ("move off-platform", "snaaaap me", "block"),
 ("secrecy / isolation", "don't tell your parents", "block"), ("secrecy / isolation", "dont tell ur parents", "block"), ("secrecy / isolation", "this is our little secret", "block"),
 ("secrecy / isolation", "keep this between us", "block"), ("secrecy / isolation", "are you alone", "block"), ("secrecy / isolation", "are your parents home", "block"),
 ("secrecy / isolation", "is anyone home with you", "block"), ("secrecy / isolation", "delete this message", "block"), ("secrecy / isolation", "no one has to know", "block"),
 ("secrecy / isolation", "your teacher doesn't need to know", "block"), ("secrecy / isolation", "are you home alone", "block"), ("secrecy / isolation", "when do your parents get home", "block"),
 ("secrecy / isolation", "dont tell your teacher", "block"), ("secrecy / isolation", "don't tell anyone", "block"), ("secrecy / isolation", "don\u2019t tell your parents", "block"),
 ("images / camera / meeting", "send me a pic", "block"), ("images / camera / meeting", "send me a photo of yourself", "block"), ("images / camera / meeting", "send pics", "block"),
 ("images / camera / meeting", "show me your face", "block"), ("images / camera / meeting", "turn on your camera", "block"), ("images / camera / meeting", "let's video chat", "block"),
 ("images / camera / meeting", "what do you look like", "block"), ("images / camera / meeting", "let's meet up", "block"), ("images / camera / meeting", "come to my house", "block"),
 ("images / camera / meeting", "I can pick you up from school", "block"), ("images / camera / meeting", "what are you wearing", "block"), ("images / camera / meeting", "you're so cute", "block"),
 ("images / camera / meeting", "can I see a selfie", "block"), ("images / camera / meeting", "I'll buy you robux if you", "block"), ("images / camera / meeting", "I'll send you a gift card", "block"),
 ("images / camera / meeting", "meet me after school", "block"), ("images / camera / meeting", "do you want to hang out irl", "block"), ("images / camera / meeting", "I love you, you are my girlfriend", "block"),
 ("images / camera / meeting", "can we meet in person", "block"), ("images / camera / meeting", "pic of u?", "block"), ("images / camera / meeting", "send me a pic of your feet", "block"),
 # legit class messages that must pass
 ("benign class talk (must pass)", "How old is this design? It was made in 2019", "pass"), ("benign class talk (must pass)", "Where do I find the infill setting?", "pass"),
 ("benign class talk (must pass)", "What age group is this lesson for?", "pass"), ("benign class talk (must pass)", "Which school project is due?", "pass"),
 ("benign class talk (must pass)", "Can you send me the STL file in class?", "pass"), ("benign class talk (must pass)", "Let's meet at the printer after lunch", "pass"),
 ("benign class talk (must pass)", "Call it a day and clean the bed", "pass"), ("benign class talk (must pass)", "Are you alone on that printer or sharing?", "pass"),
 ("benign class talk (must pass)", "I'm from Chicago, our school printer is the Prusa", "pass"),
]
for cls, t, exp in MS: T("Minor-safety: " + cls, cls, t, exp, anyblock)

# ---- fixed abusive evasion combos in context (masked, built from lists)
ctx = [("stem word in sentence", lambda w: f"you are such a {w}"), ("stem word + punctuation", lambda w: f"{w}!!!"),
       ("stem word then URL-ish", lambda w: f"{w}.com")]
for cls, fn in ctx:
    T("Abusive control", cls, fn(sample_stem), "block", anyblock, sens=True)

# ------------------------------------------------------------------ performance / robustness
print("\n== F. performance / robustness ==")
perf = []
def timed(label, text, fn=S.scan):
    t0 = time.perf_counter(); fn(text); dt = time.perf_counter() - t0
    perf.append({"input": label, "chars": len(text), "seconds": round(dt, 3)}); print(f"{label:55s} {len(text):8d} chars  {dt:7.3f}s")
for n in (1_000, 5_000, 10_000):
    timed(f"{n} x 'a' (one long word)", "a" * n)
    timed(f"{n//2} x 'a ' (spaced single letters)", "a " * (n // 2))
    timed(f"{n//5} x 'word ' (plain text)", "word " * (n // 5))
timed("20000 x 'a' w/o '@' (email regex backtracking)", "a" * 20_000, S.scan_contact)
timed("30000 x '1 ' digits (phone regex)", "1 " * 15_000, S.scan_contact)
timed("20000 x 'a.' (url regex)", "a." * 10_000, S.scan_contact)
timed("5000 x 'snap ' (handle regex)", "snap " * 5_000, S.scan_contact)
timed("30000 x 'a' + '@' (email regex)", "a" * 30_000 + "@", S.scan_contact)
timed("20000 chars of 'x' fullwidth (one word)", "ｘ" * 20_000)
timed("200000 chars, normal prose with spaces", "hello world " * 16_666)
RESULTS["sweeps"]["performance"] = perf

# empty/odd inputs: no crash
odd = ["", None, " ", "\x00", "\ud800" if False else "\ufffd", "🙂" * 50, "\n\n\n"]
crash = []
for o in odd:
    try: S.scan(o)
    except Exception as e: crash.append(repr(o) + " -> " + type(e).__name__)
RESULTS["sweeps"]["odd_inputs_crashes"] = crash
print("odd-input crashes:", crash)

# ------------------------------------------------------------------ summary
from collections import Counter
byc = {}
for r in RESULTS["fixed"]:
    d = byc.setdefault(r["cat"], Counter()); d["ok" if r["ok"] else "FAIL"] += 1
print("\n== fixed-case results by category ==")
for k, v in byc.items(): print(f"{k:50s} ok={v['ok']:3d} fail={v['FAIL']:3d}")
RESULTS["summary"] = {k: dict(v) for k, v in byc.items()}
OUT.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwrote", OUT)
