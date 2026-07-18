# CraftLint Pro — Stripe demo and launch runbook

CraftLint Pro is one recurring plan: **$9.99 USD/month**, no annual plan and no
free trial. Checkout is Stripe-hosted. Eligible payment methods are dynamically
managed by Stripe; promotion-code entry is enabled even though no codes exist
yet. Paid checkout is blocked for users under 18.

## Current verified state

- The test product and monthly price are active.
- The default customer portal supports payment-method updates, invoice history,
  and cancellation.
- The Render backend is live at `https://craftlint.onrender.com`.
- The old Railway webhook URL is obsolete and must not be used.
- The Stripe account has not completed activation. Test mode can be exercised,
  but live charges/payouts require Stripe onboarding.
- A secret test key was pasted into chat on July 17, 2026. **Rotate it before
  continuing and never deploy or reuse that exposed key.**

## Dashboard configuration — test mode

### 1. Rotate the exposed test secret

In Stripe Dashboard test mode, go to Developers → API keys, roll/expire the
exposed secret, and create/reveal a replacement. Put it directly in local/Render
secret storage. Never paste it into chat, source control, Vercel, or a
`NEXT_PUBLIC_*` variable.

The publishable key is not used by this app.

### 2. Confirm the product

- Product: **CraftLint Pro Subscription**
- Price: **$9.99 USD**
- Type: **Recurring, monthly**
- Trial: **None**
- Tax behavior for demo: leave automatic Stripe Tax disabled

### 3. Register the test webhook

Endpoint:

```text
https://craftlint.onrender.com/api/billing/webhook
```

Subscribe to:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `customer.subscription.resumed`
- `invoice.paid`
- `invoice.payment_failed`
- `invoice.payment_action_required`

Copy this endpoint's signing secret (`whsec_...`). It is different from the
temporary secret printed by `stripe listen`.

### 4. Configure Checkout and payment methods

In Settings → Payment methods, enable every Stripe-hosted method that is eligible
for a USD recurring subscription and appropriate for the business. Cards, Apple
Pay, Google Pay, and Link can appear dynamically when the customer/device is
eligible. The backend intentionally does not hard-code a narrow method list.

Promotion-code entry is already enabled in code. No coupon or promotion code is
needed for the demo.

### 5. Configure the customer portal

- Payment-method updates: **On**
- Invoice history: **On**
- Cancel subscription: **On**
- Cancellation timing: **At the end of the billing period**
- Plan switching: **Off** (there is only one plan)

### 6. Configure recovery and email

- Billing → Revenue recovery → enable **Smart Retries**
- Final action after the retry cycle: **Cancel the subscription**
- Enable Stripe successful-payment receipts
- Keep CraftLint/Brevo action-needed emails enabled for failed payments and
  cardholder authentication

Do not publish `craftlint@gmail.com` until that exact address is created and
controlled. Keep the existing owned support address until then.

### 7. Customer-facing account settings

- Public business name: **CraftLint**
- Card statement descriptor: **CRAFTLINT PRO**
- Website: `https://surge-chi-khaki.vercel.app` until the custom domain is ready
- Terms: `https://surge-chi-khaki.vercel.app/terms`
- Privacy: `https://surge-chi-khaki.vercel.app/privacy`

Update the Stripe URLs and the app's `FRONTEND_URL`, `ALLOWED_ORIGINS`, and
`NEXT_PUBLIC_SITE_URL` together when the custom domain launches.

## Render secrets — test mode

Set these directly in the Render service:

```text
STRIPE_SECRET_KEY=sk_test_...rotated replacement...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...dashboard endpoint secret...
FRONTEND_URL=https://surge-chi-khaki.vercel.app
```

No Stripe key belongs in Vercel because the browser never talks to Stripe
directly.

## Required demo scenarios

Use Stripe test data only:

- Successful card: `4242 4242 4242 4242`
- Generic decline: `4000 0000 0000 0002`
- 3D Secure: `4000 0027 6000 3184`
- Renewal failure: `4000 0000 0000 0341` with a Stripe test clock/simulation

Verify:

1. Successful checkout activates Pro only after the signed webhook.
2. Refreshing or replaying the success URL cannot grant Pro.
3. A decline creates no subscription/access.
4. 3D Secure completes and activates correctly.
5. A failed renewal triggers Stripe retries and one CraftLint action email.
6. Updating the card in the portal recovers the subscription.
7. Canceling keeps Pro through the paid period and the UI says when it ends.
8. At period end, the cancellation webhook returns the user to Free.
9. Duplicate webhook delivery does not duplicate state or email.
10. A user under 18 receives HTTP 403 and cannot open paid checkout.

Run the local automated checks:

```bash
cd backend
source venv/bin/activate
GEMINI_API_KEY=test python -m dotenv -f .env run -- \
  python -m unittest tests.test_billing tests.test_rate_limit
```

## Tax and live activation

Standard Stripe Tax can calculate and collect configured taxes, but it does not
by itself create the business, determine every registration obligation, or make
an unregistered seller automatically compliant. Keep automatic tax off for the
demo. Before live sales, determine where CraftLint must register, complete the
relevant registrations, then configure Stripe Tax/filing for those jurisdictions.

For live mode:

1. Complete Stripe identity/business and payout onboarding.
2. Create/confirm the live product and $9.99 monthly price.
3. Create the same webhook in live mode.
4. Replace all three Render Stripe values together with `sk_live_...`, the live
   `price_...`, and the live endpoint's `whsec_...`.
5. Run one real purchase, verify the receipt/portal/webhook, cancel it, and refund
   that operator test manually.
