# Independent clock for the approved Threads campaign

Vercel invokes three authenticated daily endpoints. They arm the existing GitHub
publisher before each due time; they never call Threads or hold its credentials.
The approved calendar remains 08:30, 13:00 and 20:00 Asia/Jakarta through
20 April 2027. No existing caption, media, approval or publication receipt changes.

Vercel Hobby clocks can arrive anywhere within the selected hour. The clocks
start at 07:00, 12:00 and 19:00 WIB. The GitHub worker starts before publication,
waits for the exact approved due time, reloads the current ledger and token, and
uses the existing publisher. The original GitHub cron remains a fallback. This
does not depend on a local computer. Provider outages can still delay a run.

All publisher paths share the existing account-level concurrency lock. Queued
runs check out current main; waiting runs refresh main again before publishing.
Published, missed or ambiguous records are never retried blindly. Duplicate
clock invocations reuse an already queued/running worker for the same due time.
The previous no-catch-up policy remains in force.

The service uses production-only sensitive environment variables CRON_SECRET
and GITHUB_DISPATCH_TOKEN. Neither belongs in Git or client assets. The endpoint
requires the cron secret even for dry runs. `GET /api/arm?slot=0830&dry_run=1`
verifies the approved calendar and ledger without dispatching or publishing.

Run `npm test` here and `PERSIST_GIT=0 python3 -m unittest -v` in the parent.
