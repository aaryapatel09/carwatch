# Native companion verification — 2026-10-26

Status: local prototype. No app-store submission, public API deployment, physical camera capture, or external push send was performed for this change.

| Check | Evidence / limit |
| --- | --- |
| Existing CV/research regressions | 112 tests passed locally. |
| New API and relay | 16 tests passed: per-account evidence isolation, hashed credentials, invitation/pair expiry and single use, generated JPEG review, demo suppression, push registration ownership, cancellation, retry/cooldown/expiry, mocked provider HTTP requests, crash recovery, and camera stop on disconnect. |
| Mobile logic | 3 tests passed: HTTPS origin policy, offline monitoring status, and notification event-ID validation. |
| Static checks | TypeScript, ESLint, Python Ruff and formatting passed. |
| Platform JavaScript | Expo Metro exported iOS, Android, and browser bundles. This is not a signed native-binary build. |
| Browser interaction | Welcome, offline demo, activity detail, feedback, settings, exit demo; real local-API sign-in, private feed, saved review and sign-out verified. The UI review was confirmed in SQLite. |
| Native binary | iOS prebuild generated successfully; CocoaPods dependency extraction failed because the machine ran out of disk space. Generated native files from that attempt were removed. No successful simulator install or Android binary build. |
| Push delivery | Request/queue handling tested with mocked Expo transport. APNs, FCM, phone background/lock-screen behavior, permission prompts and physical receipt remain unverified. |
| API dependencies | `pip check` passed; `pip-audit -r server/requirements.txt --no-deps --disable-pip` found no known advisories at the time of this check. |

UI testing found and fixed an overlapping `/` route that looped on sign-out. Station testing found and fixed a remaining-time condition that prevented one-minute sessions from starting. Pairing can be resumed for an existing unpaired camera without creating another camera record.

## Known dependency advisories

The current npm audit reports **five high-severity package entries**, stemming from two transitive findings: [node-forge signature validation](https://github.com/advisories/GHSA-86w9-cpqp-85rv) and [Zod constrained-collection memory exhaustion](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). The other entries propagate through Expo CLI / code-signing packages and Expo. The installed paths include the development/build toolchain; this is not a clean security audit or a production-readiness claim.

At verification, node-forge 1.4.0 was the available latest package, while the Expo CLI requested Zod 3.x. Blindly forcing a major-version override or npm's suggested Expo downgrade was not applied. Recheck upstream supported fixes before external distribution. Keep the local development server on loopback and do not use this toolchain to process untrusted signing material.

## Next evidence needed

1. A native iOS and Android build with sufficient disk/toolchain resources or an explicitly configured EAS account.
2. App launch, SecureStore restoration, pairing, permission denial/recovery, account/camera deletion confirmations, notification routing and background behavior on target devices.
3. A reachable HTTPS API with operator-controlled credentials and retention; then an explicit test notification confirmed on each phone.
4. A calibrated target camera and permissioned recordings measuring event recall, false alerts, low light, blind spots and end-to-end latency.

Neither these software checks nor the original CV development probe establishes safety performance. The mobile feedback records do not train a model automatically. The earlier proposed persistent-scene-change feature is not included in this native-app increment.
