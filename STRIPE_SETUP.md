# Surge Pro — Stripe setup

The **code** for Surge Pro ($9.99/mo) is built, wired, and tested. What's left is
the dashboard + environment work that can only be done in your accounts. This
doc maps every step. Until the env vars are set, the billing routes return 503
and nothing else is affected — so you can deploy the code first and flip billing
on whenever you're ready.

## What's already done (code)

- **Schema:** `users.stripe_customer_id / stripe_subscription_id /
  subscription_status / subscription_current_period_end` (self-migrating).
- **Backend:** `services/stripe_billing.py` + `routers/billing.py`
  - `POST /api/billing/checkout` → Stripe-hosted Checkout URL (auth required)
  - `POST /api/billing/portal` → Stripe billing portal (manage/cancel)
  - `GET  /api/billing/status` → this user's plan
  - `POST /api/billing/webhook` → **signature-verified**; the ONLY writer of Pro state
- **Enforcement (server-side, never the client):** Free = **3 analyses / calendar
  month**; Pro = **unlimited**. `services/rate_limit.py`.
- **Frontend:** Upgrade button, `/billing/success`, `/billing/cancel`, a billing
  card in Settings, and the monthly-allowance bar with an upgrade nudge.
- **Webhook events handled:** `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`,
  `invoice.payment_failed` (flags `past_due` + emails the user).
- **Tests:** `backend/tests/test_billing.py` (signature verification + full
  lifecycle), `test_rate_limit.py` (free 3/mo, Pro unlimited).

---

## Step 1 — Stripe account & keys (you)

1. Create / sign in at https://dashboard.stripe.com. Stay in **Test mode** (toggle, top-right) for now.
2. Developers → API keys → copy the **Secret key** (`sk_test_…`). The publishable key is **not needed** (we use hosted Checkout).

## Step 2 — Product & price (you)

1. Product catalog → **Add product** → name **"Surge Pro"**.
2. Add a **recurring** price: **$9.99 / month**.
3. Copy the **Price ID** (`price_…`).

## Step 3 — Webhook endpoint (you)

1. Developers → Webhooks → **Add endpoint**.
2. URL: `https://surge-production-8973.up.railway.app/api/billing/webhook`
3. Select events: `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`.
   (`customer.subscription.created` is also handled if you add it — optional.)
4. Copy the **Signing secret** (`whsec_…`).

## Step 4 — Environment variables (you)

Set these in **Railway** (backend). No frontend Stripe keys are required.

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

`requirements.txt` already includes `stripe`, so the next backend deploy installs
it. `FRONTEND_URL` (already set) is used for the success/cancel redirect URLs.

---

## Step 5 — Test before going live (test mode)

Test card numbers (any future expiry, any CVC, any ZIP):
- ✅ success: `4242 4242 4242 4242`
- ❌ declined: `4000 0000 0000 0002`

### Local end-to-end with the Stripe CLI (recommended)

```bash
# 1. Run the backend with your TEST keys.
cd backend && source venv/bin/activate
STRIPE_SECRET_KEY=sk_test_... STRIPE_PRICE_ID=price_... \
STRIPE_WEBHOOK_SECRET=whsec_localcli... \
uvicorn main:app --reload --port 8000

# 2. Forward webhooks to localhost (prints a whsec_… to use above).
stripe listen --forward-to localhost:8000/api/billing/webhook

# 3. From the app, click "Upgrade" → pay with 4242…  → you should land on
#    /billing/success and Settings should show "Surge Pro ✦".
```

### Checklist (maps to your original list)
- [ ] Successful payment (`4242…`) → user becomes Pro; `/api/billing/status` shows `is_pro: true`.
- [ ] Failed payment (`4000 0000 0000 0002`) → checkout blocks; subscription not created.
- [ ] Cancel via the billing portal → `customer.subscription.deleted` → user back to free.
- [ ] `invoice.payment_failed` → status flips to `past_due` and the user is emailed.
- [ ] Free tier blocks correctly **after 3 analyses in a month** (covered by `test_rate_limit.py`).
- [ ] Pro tier has **no** analysis limit (covered by `test_rate_limit.py`).
- [ ] Stripe dashboard → Developers → Events/Webhooks shows 2xx responses, no errors.

## Free Pro for yourself (owner / testers) — no payment

Set **`COMP_PRO_EMAILS`** in Railway (and in `backend/.env` for local) to a
comma-separated list of emails that should get **unlimited Pro for free, no
Stripe**:

```
COMP_PRO_EMAILS=you@example.com,tester@example.com
```

Then sign up / log in with that exact email — your account is unlimited
immediately (Settings shows "Complimentary Pro ✦"). This is server-side only, so
no one can grant it to themselves; only the real holder of a listed address gets
it. Case-insensitive. Use addresses you control. Changing the list takes effect
on the next backend restart/redeploy. This works even before Stripe is set up, so
you can fully test the product right now.

## Step 6 — Go live

1. In Stripe, flip to **Live mode** and repeat Steps 1–3 to get **live** keys, a
   live Price ID, and a live webhook signing secret.
2. Replace the three Railway env vars with the `sk_live_… / price_… / whsec_…`
   live values. Redeploy.
3. Do one real $9.99 purchase to confirm, then refund it from the dashboard.

## Notes

- **Security:** the webhook verifies Stripe's signature on the raw body before
  doing anything; a forged "you're Pro" POST is rejected with 400. Pro status is
  only ever written by that verified webhook — the client can't grant itself Pro.
- **Grace period:** `past_due` keeps Pro access while Stripe retries the card;
  access ends when Stripe finally emits `customer.subscription.deleted`.
- **Cost watch:** Pro is genuinely unlimited, so a Pro user's analyses are
  uncapped Gemini spend. Monitor `usage_events` / the admin operations report.
