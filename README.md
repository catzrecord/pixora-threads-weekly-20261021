# Threads @1fatherx: six-month campaign

Owner-authorized on 21 October 2026: 546 posts, 21 October 2026 through 20 April 2027, at 08:30 / 13:00 / 20:00 WIB. The owner additionally instructed “ok aktifkan”. Existing TEST-01…TEST-21 IDs and receipts are preserved; added slots use SIX-022…SIX-546. Publication stops at the end of 20 April WIB.

Every slot has finished conversational Indonesian sales copy, one real image and one real video, fixed hashes and public release URLs. Copy uses gw/lo, sells tools first, omits product names and ends with komen mau. WhatsApp supports the offer with campaign information and clipper tips. No free access, price, subscription, fixed output count, guaranteed viral or income claims are made.

This cloud dispatcher uses Meta's official Threads API. It is not a reservation in Threads' native interface. GitHub Actions supplies the timer and durable receipts. Scheduled times are targets; Actions can start late. More than thirty minutes late is recorded as missed, without a catch-up burst. At most one due post is published per run. Retry invocations cannot duplicate published or ambiguous jobs. PUBLISH_ENABLED=true, verified account @1fatherx, valid credentials, available quota and exact hosted media bytes are required.

approval.json records the extension instruction and pins schedule.json. Every date/time, ID and carousel is checked before API calls. state.json records container IDs and publication IDs. Publishing intent is pushed before the publish call. An ambiguous response becomes needs_reconciliation and is never blindly retried.

## Media and ongoing production

The initial library has 35 distinct real images and 26 distinct videos: genuine screenshots, real-photo/screenshot composites, three historical screen-recording excerpts, three verified output examples, and twenty credited podcast-practice excerpts. Proof material is intentionally reused. These are not 546 unique videos or fresh app runs. Silent historical screen recordings retain their original audio state.

The first 21 posts stay intact. Thirteen additional recent practice excerpts fill evening slots through 9 November. Other future slots already have genuine owned proof media. A practice caption includes its source URL and is not described as a new tool output.

At 21:17 WIB daily, producer.py checks the upcoming seven days, rotates fourteen public channels, and attempts at most two new clips. Episodes must have at least 10,000 observed views, last at least twenty minutes, and be at most 21 days old on the scheduled posting date. Public chapter/replay information and original-language captions are required. Views are an observation, not a future trending claim.

Each practice excerpt preserves the original frame and audio for ninety seconds: no added hook, subtitle, crop, CTA, music, AI background or speed change. Stream duration, frames, full decode and hosted bytes are verified before changing an untouched future slot. Started, published, ambiguous and near-due jobs are excluded. Source failure preserves the already attached real proof media. production.json records attempts and provenance. No future source is called produced before its actual media pass checks.

## Credentials

Daily maintenance checks the token and renews it when twenty days old or with twenty days remaining. token.enc contains authenticated Fernet ciphertext. Its key is only in GitHub Actions encrypted secret THREADS_TOKEN_VAULT_KEY and the owner's local restricted secret directory. A renewed credential is checked against @1fatherx, encrypted and pushed before reporting success. Plaintext credentials are never committed. Revoked or expired authorization fails closed and requires owner reauthorization.

## Checks and operation

python -m unittest -v covers campaign bounds, account identity, exact carousel content, hosted bytes, duplicates, ambiguous outcomes, source age, encrypted storage and renewal. Set PERSIST_GIT=0 for tests. publisher.py --mode check verifies account/quota without publishing. preflight additionally verifies first-day hosted media. Manual workflow mode roll runs maintenance and rolling production without publishing; due publishes only a currently due approved slot.

Local review: /Users/coong/Documents/Threads-1fatherx-6Bulan-20261021. The local gallery is a delivery snapshot; this repository is the current schedule and receipt authority as source credits/media refresh. The older annual producer is superseded and must not run alongside this dispatcher.

Primary references:
- Meta Threads API and refresh: https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api
- Scheduled workflow behavior: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Authenticated encryption: https://cryptography.io/en/latest/fernet/
