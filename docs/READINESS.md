# Release-readiness audit

Target: a reproducible GitHub repository for the complete current Carwatch prototype, with its implemented behavior tested and unsupported capabilities stated accurately. The broader request for a perfect, fully validated safety system remains unproven.

## Release evidence

| Requirement | Evidence / status |
|---|---|
| Source is reviewable and versioned | Git history; formatted Python; no generated weights/videos tracked |
| Fresh setup works | Lock-file installation and full suite in a separate Python 3.11 environment |
| Main workflow works | Actual pretrained pose inference → saved clips → human labels → dataset export integration check |
| Custom training works | Generated-pattern exercise and checkpoint/inference tests; **no real car-door model trained** |
| Failure paths are handled | Camera process termination, unavailable camera, invalid video metadata, failed codecs, interrupted evidence writes, and concurrent-review regressions |
| Data isolation is preserved | Explicit dataset origin, session/hash split validation, duplicate-run checks, isolated UI tests |
| Model artifacts remain consistent | File lock, immutable generation artifacts with atomic card publication, replacement-failure regressions, weights-only loading, and checksum/card validation |
| Credentials/private footage stay out of Git | Ignore rules plus tracked-file hygiene check; review the final diff before publication |
| Licensing and contributor/security guidance exist | LICENSE, CONTRIBUTING.md, SECURITY.md and source/model-license notes |
| CI definitions validate | Pinned official action revisions, least-privilege jobs, local actionlint check |
| Hosted CI is green | Implementation commit `08ac9e4` passed [112 tests and repository checks](https://github.com/aaryapatel09/carwatch/actions/runs/40427307711) and [CV integration with all three public-video configurations](https://github.com/aaryapatel09/carwatch/actions/runs/40427307257). Inspect workflow runs for later commits. |
| Actual camera hardware works | **Not established: no physical camera activated** |
| Behavior detection works on real independent footage | **Not established.** A public MEVA development probe documented missed people (0/17 full-frame; 7/17 with a region selected afterward; 9/17 with a larger detector on that region). Independent intended-camera evaluation remains absent. |
| Notification sending software works | Optional live-session ntfy sender: local HTTPS acknowledgement, TLS rejection, retry/cooldown/expiry, cancellation, interrupted-send uncertainty and redaction checks. No real service or phone tested. |
| Universal mounting, power, heat, LTE and phone receipt work | **Not implemented or validated on hardware** |
| “100% perfect” | **Not a property that finite testing can prove** |

## Next evidence needed

1. Verify both checked-in workflows pass for the exact commit being released.
2. Exercise opt-in camera acquisition, preview, automatic time limit, explicit Stop and disconnect behavior with intended hardware.
3. Collect permissioned, independently split car-side recordings with ordinary activity and target interactions; review consistent labels and train/evaluate real models.
4. Measure event recall, false alerts per hour, latency, low-light/weather behavior and blind spots using complete independent recordings, not only selected positive windows.
5. Complete and test the missing hardware, connectivity and phone-delivery components before making a product-readiness claim.

Passing local repository checks does not satisfy the outstanding product requirements. No camera or external notification should be activated merely to improve a test count.
