# Optional phone alerts

Carwatch can publish text-only activity cues to a configured ntfy server during an explicitly enabled live-camera session. This feature is **off by default**. It has been tested against a loopback HTTPS receiver, not an external ntfy service or a physical phone. A service acknowledgement never means the phone received or displayed a notification.

## Configure the destination

Use an HTTPS ntfy server and a topic protected against anonymous read and write access. Authentication alone does not make a topic private: configure access rules on the server. For a self-hosted instance, ntfy documents a private configuration using `auth-default-access: deny-all` with explicit user/topic permissions. Give Carwatch a token limited to publishing to that topic and configure the phone with appropriate read access. [Official access-control instructions](https://docs.ntfy.sh/config/#access-control), [publishing authentication](https://docs.ntfy.sh/publish/#authentication).

Subscribe to the same server and topic in the ntfy phone app. Follow the provider's platform-specific instructions, including its iOS setup for self-hosted servers. Do not assume background delivery works merely because subscribing succeeded. [Official configuration guide](https://docs.ntfy.sh/config/).

Set these environment variables **before starting Streamlit**:

- `CARWATCH_NTFY_SERVER`: HTTPS origin, such as `https://notify.example.invalid`, without a topic, query or embedded password.
- `CARWATCH_NTFY_TOPIC`: protected topic name, 3–64 letters, digits, hyphens or underscores.
- `CARWATCH_NTFY_TOKEN`: publishing access token.
- `CARWATCH_NTFY_PRIVATE=1`: your confirmation that the topic's access rules are private. Carwatch validates the configuration format; this flag does not remotely verify those rules.

The checked-in `.env.example` contains placeholders. Copy it to an ignored `.env` file without overwriting an existing configuration, fill in your settings, then load the file in the shell before starting the app. The app does not automatically load `.env` files. Never commit the real token. Tokens are kept out of the app's journals and camera metadata.

In **Live camera**, explicitly enable the text-alert checkbox and start a permissioned camera session. A disabled checkbox means configuration is absent or invalid. Recorded-video analysis, example clips, synthetic model training and opening the dashboard never send notifications.

## Delivery behavior

The payload contains only a fixed description of the observed cue and its UTC time. It includes no images, video, audio, camera name, location, track ID or model score. HTTPS certificate verification is required; redirects are rejected. The configured service sees the connection and message, and its own retention and mobile push-provider policies apply.

The sender runs separately from camera inference. It records at most 100 cues per session, suppresses the same cue type for 30 seconds, and makes at most three attempts within a 60-second queue lifetime. Network failures and temporary service errors can be retried. A timeout can occur after the service accepted a request, so retries can produce duplicates. Unrecognized acknowledgements remain unconfirmed.

Stop and the session time limit cancel unsent work. An in-flight request may already have reached the service; it remains unconfirmed locally if interrupted. Pending messages are not resumed after a restart. The local `live/<session>/alerts.json` journal records accepted, suppressed, expired, cancelled, failed and unconfirmed attempts. “Accepted” only records the service's acknowledgement. Read the timestamp on a phone notification: provider or device delays can outlast Carwatch's sending window.

## Verification still needed

Run `python scripts/verify_alerts.py` to exercise the sender and dispatcher with an ephemeral local HTTPS receiver and test credentials. It also checks that an untrusted certificate is rejected. No real message is sent externally.

Before relying on phone delivery, test the intended service, subscribed phone, locked/background state, network loss/reconnection, Stop, expired messages and notification permissions. Camera acquisition, field detection quality, LTE connectivity and physical-phone receipt remain unverified. No delivery state or absence of messages establishes safety.
