# Optional Semi Pro and Pro (Stripe)

Core ZEIM stays free. Semi Pro and Pro are optional monthly plans that help fund hosting.

| Plan | Price | ZEIM service fee (about 1%, nearest cent) |
|---|---|---|
| Free | $0 | none |
| Semi Pro | $3.50 / month | 4¢ / month |
| Pro | $5.50 / month | 6¢ / month |

ZEIM does **not** store card numbers, CVC, expiry, or payment methods. Checkout and the billing portal are hosted by Stripe. ZEIM stores, on the account record:

- `plan`: `free`, `semi_pro`, or `pro` (this is what feature gates read)
- `billing.customer_id`: Stripe Customer id (`cus_...`)
- `billing.subscription_id`: Stripe Subscription id (`sub_...`)
- `billing.status`: Stripe's status (`active`, `past_due`, `canceled`, ...)
- `billing.cancel_at_period_end`

Billing is not a login reset. See [Account access](#account-access) below. Soft launch keeps `ZEIM_PLANS_ENABLED` unset or `0`, so these plans stay Coming later until that flag is explicitly turned on.

## How ZEIM knows who paid

1. The signed-in account id is sent to Stripe as Checkout `client_reference_id` and as metadata `zeim_user_id` on the Customer and the Subscription.
2. Stripe hosts the card form. ZEIM never receives the card.
3. Stripe posts signed events to `POST /api/subscriptions/webhook`.
4. The webhook writes `plan` and the Stripe ids. A browser return to `/?checkout=success` does **not** mark anyone paid.
5. Feature gates call `has_paid_plan` (2D→3D Pro mode uses `ai3d.is_pro`, which reads that same `plan` field).

Staff can list plan status with the existing admin token (no card data, no date of birth, no email):

```bash
curl -sS -H "X-Admin-Token: $PHOTO3D_ADMIN_TOKEN" \
  "https://zeimapp.com/api/subscriptions/admin"
# one account:
curl -sS -H "X-Admin-Token: $PHOTO3D_ADMIN_TOKEN" \
  "https://zeimapp.com/api/subscriptions/admin?user_id=ACCOUNT_ID"
```

ZEIM does not keep the customer's email (sign-in stores only a hash). To find a payer in Stripe: ask them for the email they typed at Checkout, then in the Dashboard search **Customers** by that email. Confirm metadata `zeim_user_id` matches the user id from the admin list. You can also search `metadata['zeim_user_id']:'ACCOUNT_ID'`.

## Monthly renewal, cancel, and failed payments

Checkout is `mode=subscription`. Stripe Billing renews the plan price and the service-fee line every month. ZEIM does not run its own charge cron.

| Stripe event | What ZEIM does |
|---|---|
| `checkout.session.completed` (paid) and `checkout.session.async_payment_succeeded` | Set the paid tier |
| `customer.subscription.created` / `updated` | Set Semi Pro or Pro while status is `active`, `trialing`, or `past_due` |
| `invoice.paid` | Mark the subscription active and keep the tier |
| `invoice.payment_failed` | Mark `past_due`. The tier stays while Stripe retries. The account page says so |
| `customer.subscription.updated` with `cancel_at_period_end` | Keep the tier until the period ends. The account page says it will cancel |
| `customer.subscription.deleted` (and statuses `canceled`, `unpaid`, `incomplete`, `incomplete_expired`, `paused`) | Set the account back to Free |

Cancel, switch Semi Pro ↔ Pro, or replace the card in the Stripe Customer Portal (Account → **Manage billing in Stripe**) or in the Dashboard. That portal is not a ZEIM login.

## Account access

Sign-in is a passkey, a password, or an email code. See [docs/auth.md](../auth.md). Canceling a plan is not a password reset.

- Sign in with a **passkey**, a **password**, or an **email code** when SMTP is configured.
- Older cookie accounts may still have a one-time recovery code.
- The Stripe ids live on that same account. Signing back in keeps the plan.
- A brand-new account does not inherit someone else's subscription. Support matches them in the Dashboard by email and `zeim_user_id`; this app does not move subscriptions between accounts by itself.

## Service fee (not a marketplace cut)

The ~1% fee is a **second recurring line** on ZEIM's own subscription (inline Price, unless `STRIPE_PRICE_FEE_*` is set). The whole charge is paid to ZEIM's Stripe account. Stripe then takes its processing fee from that charge.

This is not a Connect application fee. Application fees are for a platform taking a cut of someone else's charge. ZEIM does not use Connect here and does not take a cut of creator tips or Showcase sales. Tips stay direct links (PayPal / Venmo / Cash App) on the creator's profile.

Stripe's processing fee is **not** a guessed extra line. It depends on the payment method (card vs wallet vs PayPal vs Cash App Pay). The account page and the Checkout button say the customer covers Stripe's fee and ZEIM does not keep it. Sales tax is off (`automatic_tax` is not enabled). Turn tax on only after a Stripe Tax registration exists.

## Payment methods

Checkout does not send `payment_method_types`. Stripe shows whatever is turned on in the Dashboard for a monthly US subscription.

Hosted Checkout runs on `checkout.stripe.com`, so the card form is not on zeimapp.com.

1. Dashboard → **Settings → Payment methods**.
2. Leave **Cards** on. Apple Pay and Google Pay are wallets on that card form. On hosted Checkout they use Stripe's domain; you do not upload an Apple Pay domain file for zeimapp.com unless you later embed a card form on ZEIM (this app does not).
3. Optional: turn on **PayPal** and **Cash App Pay**. They show on this Checkout page only when Stripe allows that method for a monthly subscription. If a toggle is on and the method is one-time only, Stripe simply does not offer it. ZEIM does not force it.
4. Save. Test mode and live mode have separate settings. Repeat in the mode you are using.

## What Zach creates in the Dashboard

Do this once in **test mode**, then again in **live mode** with live keys. Prices are not shared between modes.

1. **Products**
   - Product `ZEIM Semi Pro`, recurring Price **$3.50 USD / month**. Copy the Price id (`price_...`) to `STRIPE_PRICE_SEMI_PRO`.
   - Product `ZEIM Pro`, recurring Price **$5.50 USD / month**. Copy the Price id to `STRIPE_PRICE_PRO`.
   - ZEIM refuses Checkout if those amounts are not exact, so a misplaced Price cannot silently charge something else.
   - Optional: monthly Prices of **$0.04** and **$0.06** for the service fee (`STRIPE_PRICE_FEE_SEMI_PRO`, `STRIPE_PRICE_FEE_PRO`). If you leave those blank, ZEIM adds the fee itself at those amounts.
   - Do not add a product for tips or Showcase sales.
2. **Customer portal** (Settings → Billing → Customer portal)
   - Turn the portal on.
   - Allow customers to cancel, to update the payment method, and to switch between the Semi Pro and Pro prices.
   - Return URL: `https://zeimapp.com/#account` (or the staging origin).
3. **Webhook** (Developers → Webhooks → Add endpoint)
   - URL: `https://zeimapp.com/api/subscriptions/webhook`
   - Events:
     - `checkout.session.completed`
     - `checkout.session.async_payment_succeeded`
     - `checkout.session.async_payment_failed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.paid`
     - `invoice.payment_failed`
   - Copy the signing secret (`whsec_...`) to `STRIPE_WEBHOOK_SECRET`.
4. **API key** (Developers → API keys). Prefer a [restricted key](https://docs.stripe.com/keys.md) (`rk_test_` or `rk_live_`) that can write Checkout Sessions, Customers, and Billing Portal sessions, and read Prices. Put it in `STRIPE_SECRET_KEY`. The publishable key (`pk_...`) is `STRIPE_PUBLISHABLE_KEY`. Hosted Checkout does not put that key on the ZEIM page; keep it for Dashboard reference. Do not commit any of these.
5. Set `PHOTO3D_PUBLIC_BASE_URL=https://zeimapp.com` before live mode. Live Checkout refuses to start on plain http.

Local forwarding (test mode only):

```bash
stripe listen --forward-to localhost:8765/api/subscriptions/webhook
```

Use the `whsec_` that command prints. Stripe's test card `4242 4242 4242 4242` is entered on Stripe's page, not stored by ZEIM.

## Env

| Variable | Required to leave Coming | Meaning |
|---|---|---|
| `ZEIM_PLANS_ENABLED` | yes, and it defaults off | `1` allows Checkout. Unset or `0` refuses charges and keeps Coming later, even if the keys below are set. Soft launch stays `0`. |
| `STRIPE_SECRET_KEY` | yes | `rk_test_` / `sk_test_` = test mode label, no real charge. `rk_live_` / `sk_live_` = live. Prefer a restricted key. |
| `STRIPE_WEBHOOK_SECRET` | yes | Signing secret for `/api/subscriptions/webhook`. |
| `STRIPE_PUBLISHABLE_KEY` | no | Not used by hosted Checkout. Documented so it is not invented later on the page. |
| `STRIPE_PRICE_SEMI_PRO` | yes | $3.50 USD monthly Price id. |
| `STRIPE_PRICE_PRO` | yes | $5.50 USD monthly Price id. |
| `STRIPE_PRICE_FEE_SEMI_PRO` | no | Optional 4¢ monthly Price. |
| `STRIPE_PRICE_FEE_PRO` | no | Optional 6¢ monthly Price. |

If the plans flag is off, or any other required value is missing, Account → Plans stays **Coming later** and checkout does not call Stripe.

## Tests

```bash
python -m pytest -q tests/test_subscriptions.py tests/test_stripe_plans.py
```

Those tests mock Stripe. They check signature rejection, Semi Pro vs Pro mapping, the 1% fee, fee disclosure, and that card fields in a webhook are not stored.

## Not in this change

- Deploying live keys (do that on the server, not in git).
- Creator tip processing, Showcase sales, or any marketplace / Connect cut.
- Stripe Tax.
- Embedding a card form on zeimapp.com.
