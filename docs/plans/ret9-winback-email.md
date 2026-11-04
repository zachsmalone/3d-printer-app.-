# RET9: win-back email campaign (design only)

Status: design doc. No email is sent, no flag changes, and the privacy page is unchanged.

## Constraint
Cloudflare Email Sending is for transactional mail. A win-back campaign is marketing mail, so it needs a
separate email service provider (ESP) that handles marketing consent, unsubscribe and reputation.
`ZEIM_EMAIL_ENABLED` stays unset.

## Proposed design
- **Consent first:** only accounts that opted in to product news, with a clear opt-in on Account. No
  emails to anyone who hasn't opted in. This needs a privacy page update, which Zach must approve first.
- **Who:** opted-in accounts with no sign-in for 30 days. At most 2 emails per lapse, then stop.
- **What:** short, plain mail: one thing that is new and their last saved project with a link back. No
  discounts unless Zach decides on them; no invented numbers.
- **Every email:** one-click unsubscribe (List-Unsubscribe + List-Unsubscribe-Post), physical address,
  sender name ZEIM, and a link to email preferences.
- **Data shared with the ESP:** email address, first name if given, and the project title/link. Nothing else.
- **Tracking:** open tracking off; click counts only, in line with the first-party analytics stance.
- **Code:** a nightly job selects eligible accounts and posts them to the ESP's API with a dry-run mode that only
  writes a report. Behind a new default-off flag.

## ESP options (prices change; check before deciding)
| ESP | Notes |
|---|---|
| Postmark (Broadcast stream) | Separate marketing stream from transactional; strong deliverability |
| Resend (Broadcasts) | Simple API; audiences and unsubscribe built in |
| Amazon SES | Cheapest at volume; you build unsubscribe/suppression yourself |
| Buttondown / Loops | Newsletter-style tools with consent handling |

## Decisions needed (Zach)
1. Which ESP.
2. Approve the opt-in wording and the privacy page change (not changed yet).
3. Approve the email copy before any send.
