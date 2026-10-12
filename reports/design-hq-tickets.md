# Design tickets from the HQ browser test (items 4, 5, 6)

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


**Author:** Sakura Mori (Design & UX) · **Date:** 2026-10-04 · **Status:** DRAFT for Aiko's classroom check and Kenji's wording check. Only Engineering edits code.
Evidence: `previews/browser-test/09_classroom_access.png`, `07_showcase_search.png`; `static/community.js:188` (toast "Teacher tools need an adult account - sign up first"), `:78` ("Nothing here yet."), `app/branding.py:19` (SHOWCASE_TABS), `app/api/community.py:~150` (foryou hint).

## HQ-1  Teacher onboarding (browser-test item 4)  -- P0 for classroom use
**Problem:** "Teacher tools" shows only a red toast, then opens the general account dialog. That dialog says "You must be 18+... younger learners join a class" but never says it is the way to become a teacher, and nothing says what comes next. A teacher hits a dead end.
**Proposal:** one short guided dialog, "Set up teacher tools", opened by the Teacher tools button. Three plain steps, each on one screen:
1. **Make a grown-up account.** Display name (not your full name), date of birth. Help text: "Teacher tools are for adults. Students never need an account." Reuse the existing sign-up endpoint; same age rules.
2. **Make your class.** Class name, class password (offer "Make me a password" with a Show/Hide toggle; enforce the minimum length Kenji sets), and the line "Ask students to use nicknames, not real names."
3. **Share it.** Show the class code in large type, the typeable join address, and a Copy button. QR is optional and secondary (school devices often cannot scan). Say what a student does: "Go to the address, type the code, the password, and a nickname."
**States:**
- Already signed in as an adult: skip to step 2.
- Signed in as a teen/child, or DOB under 18: show a calm message instead of an error toast: "Classroom tools are for adults. You can join a class with a code from your teacher." and a Join a class button.
- Do not claim ZEIM verifies teachers. It does not. Suggested honest line (Kenji to review): "ZEIM does not check who is a teacher. Please only create a class for students you teach."
**Out of scope here (see design.md T8 and Aiko's review):** Safety tab, password reset, new class code, printable join sheet.
**Accept when:** a first-time adult, from a fresh browser, can go from Spark Lab to a working class code in three screens without reading documentation; a teen sees a friendly message and no dead end; the whole flow works by keyboard; no native `prompt()`.

## HQ-2  Rename "Free" (browser-test item 5)  -- P1
**Problem:** Everything in ZEIM is free, so a tab called "Free" is confusing and, with seed data, shows the same list as Trending.
**Proposal:** rename to **Newest** and sort by publish date (newest first), so it is genuinely different from Trending. Tab order: Trending, Newest, For You. Keep the internal tab key stable if renaming it would break stored data; change only the label in `SHOWCASE_TABS`. (Same as T4 in design.md.)
**Honesty note:** with only a few seed items the two tabs can still look alike. That is fine; do not invent counts to make them differ.
**Accept when:** the label reads Newest and the order is by date.

## HQ-3  Empty states with a reason and a next step (item 5)  -- P1
Replace the one generic "Nothing here yet." with per-case text (grade 4-5 wording; Aiko to tune):
| Where | Text |
|---|---|
| For You, personalization on, nothing learned yet | "For You fills up as you look around. Search for something or open a few projects, and ideas will show up here." |
| For You, personalization off | "For You is off. You can turn it on in Settings." (link to the setting) |
| Search with no matches | "No projects match "dino". Try a shorter word like "relief" or "lamp", or look in Trending." |
| Newest/Trending with no items | "No projects here yet. Be the first to share one when you are ready." (hide the sharing nudge for under-13 or class students) |
| Class with no projects (teacher) | "No projects yet. When students send builds, you will see them here." |
Each has one clear action button. The line under the tabs, "Items marked EXAMPLE are placeholder seed data", should become "Examples help you see how ZEIM looks. They are not made by real people." (also removes the developer word "seed", see T4).
**Accept when:** no screen in Showcase or Spark Lab shows a bare "Nothing here yet."

## HQ-4  Visible Search button (item 6)  -- P1
**Problem:** the search box works only on Enter, and on touch keyboards or for children that is not obvious.
**Proposal:** input `type="search"` with a visible **Search** button (magnifier icon plus the word on wider screens, icon with `aria-label="Search"` on narrow screens), min 44 px touch target, Enter still works, a labelled Clear (x) button, and a result line: "3 projects match "dino"" with `role="status"`. Wrap in a `<form role="search">`.
**Accept when:** a mouse, touch or keyboard user can search without knowing about Enter; Clear returns to the full list; the result count is announced.

## Flag for Engineering and Kenji (please verify, not a design call)
The EXAMPLE card in `07_showcase_search.png` appears to show a like count (168) and a download count (1500). HQ decisions say example items show **no invented counts**. If that is what the app shows, it contradicts the decision.

## Hansei
I wrote this from the screenshots and code, not from a live click-through. Wording is a draft and is not tested with real children or teachers. The three-step teacher flow assumes the existing sign-up and class-create endpoints can be chained; Engineering should say if that is not so.

---
## Revision 1 (after Kenji's and Aiko's review, 2026-10-04) -- supersedes the matching lines above

**HQ-1 teacher onboarding, final changes**
- Teacher honesty line: "ZEIM can't check who is a teacher. Please only make a class for students you teach."
- Display name help: add "Don't use an email or phone number here." Class step: add "Students use nicknames."
- The share screen does NOT show the class password by default. Tell the teacher: "The password isn't shown here. Tell your class yourself."
- Share screen: the typeable join address and the class code together in big type on one screen, with a **Print join sheet** button. QR is optional. Join screen can say "not case-sensitive" (codes skip 0/O/1/I; join accepts lowercase, per Aiko's code check).
- "Make me a password": three short, easy-to-type words, at least 8 characters.
- After the class is created, land the teacher on a **Start with Glow Card** button, not an empty dashboard.
- Build order: class creation waits for the join-limiter fix and the 8-character minimum password.
- Keep the "share one" nudge hidden for teens and class students.

**HQ-3 empty states, final change**
- For class students and teens, any empty list says "Nothing here yet. Check back soon." with no share-one nudge.

**New (from Kenji, for Engineering):** serve like/download counts as null for EXAMPLE items, hide counts for minors, keep seed numbers out of the Trending score. Design side: an example card shows no counts at all (no "0", no dash).
