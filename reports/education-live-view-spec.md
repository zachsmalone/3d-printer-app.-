# Teacher Live View: one-page spec (Spark Lab Curriculum Writer, 2026-10-04)

Status: spec for Yami's builders. Not built. Nothing here has been tested with a teacher or a child.
Assumption (from Yami): today a teacher cannot see live student progress.

## Goal
A teacher with a class open sees, at a glance, who is working on what and who needs help, without students having accounts or sharing personal data.

## Roster (per student, class-only)
| Column | Content |
|---|---|
| Nickname | the class nickname only |
| Current lesson and step | for example "Glow Card, step 3 of 6" |
| Current model | the model's name only. No photo or thumbnail (a photo can show a face) |
| Last activity | "just now", "4 min ago", "inactive 15+ min" |
| Hand | "Needs help" with an icon, or empty |

## Raise-hand
- Student taps "I need help". Optional note: pick from canned choices (Stuck on a step / Printer question / Not sure what to do). Free-text note only if it goes through the same filter as all other student text, capped at 80 characters.
- Teacher clears the flag with a "Helped" button. Students can also lower their own hand.
- The flag is shown with text and an icon, never colour alone.

## Student notice (shown when a student joins a class)
"Your teacher can see your nickname, which lesson step you are on, your model's name, and when you last did something. They cannot see your photos here."
Students see this once per join, in plain language, and can read it again from the class screen.

## Rules (privacy and safety)
1. Class-only: the server checks the requester is the teacher who owns that class. Other teachers, students and anonymous visitors get a not-found response. Do not rely on hiding the screen.
2. No photo thumbnails, no source images, no file names in the roster.
3. Only roster fields above are returned by the API. No emails, DOB or IP addresses.
4. Any student-typed text (nickname, note) passes through the existing filter. Remember the filter is a basic safety net, so teachers still supervise.
5. Activity data is deleted with the student or the class, with the same cleanup rules as build data.
6. Stop sending live updates when the teacher closes the screen.

## Accessibility (from the Accessibility & Usability Reviewer)
- Real table (or list) with named column headers.
- Hand-raised changes are announced politely to screen readers (polite live region), and a visible "Needs help" row stays until cleared.
- Updates must not reorder rows under the teacher's cursor. Keep a stable order (join order or A to Z). Offer an optional "Needs help first" sort the teacher turns on by hand.
- Works at iPad and phone widths without sideways scrolling; touch targets at least 44 by 44 px.
- Status messages stay on screen until dismissed.

## Updates
Refresh every 10 to 15 seconds (poll). No push service needed for v1.

## Tests to write
- Teacher A cannot read Teacher B's roster (404).
- A student cannot open the roster.
- Roster payload contains only the fields listed, no thumbnails.
- Hand note goes through the filter.
- Deleting a student or class removes their activity records.
- Row order stays stable when a hand is raised.

## Not verified / open
- Which step data the app already stores per student is not confirmed by me; the builders should check before promising "step" in the roster.
- Real-device behaviour (iPad, VoiceOver) is untested.
