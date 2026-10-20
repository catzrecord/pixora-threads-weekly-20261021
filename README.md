# PIXORA: approved one-week Threads test

Owner-approved copy for @1fatherx: 21–27 October 2026, three posts per day, at 08:30 / 13:00 / 20:00 WIB. Each post is one carousel containing one image and one video. Six posts combine the tools offer with WhatsApp campaign information and clipper tips.

Publication uses Meta's official Threads API, https://graph.threads.net/. GitHub Actions supplies the timer and durable receipts. It does not publish through browser automation. Schedule times are targets: GitHub Actions can start late. Jobs more than 30 minutes late are marked missed, without a catch-up burst.

The workflow remains inactive until `PUBLISH_ENABLED` is `true`, a verified @1fatherx token is configured, and media checks pass. An approved calendar alone is not proof of active publishing.

`schedule.json` holds the immutable approved captions and media hashes. `approval.json` pins its checksum. `state.json` records each container and published post ID. Publication intent is committed before the publish request; an ambiguous response requires reconciliation and will never be blindly retried. The program refuses publication outside the approved 2026 week.

Approved media are hosted in the release `approved-media-20261021`. There are 21 images and 13 distinct videos reused across the 21 posts. Original media are preserved. Source-practice videos are labelled in their captions; historical demo recordings and genuine PIXORA outputs are identified in the schedule metadata. No endorsement is implied by a podcast excerpt or a product-photo composite.

No credentials belong in this repository. Only the required access token is stored in GitHub Actions encrypted secrets. No DM, follow, comment or WhatsApp-message automation is included.

Official API reference: https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api
