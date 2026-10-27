# Private companion API and camera relay

This is a single-host invited pilot API using FastAPI and SQLite, separate from the unauthenticated Streamlit research dashboard. The mobile app can sign in, pair a station, request monitoring, review private event snapshots, and register for Expo push. Push is disabled by default.

## Local API

Run from the repository root with Python 3.11:

```sh
python3.11 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements-dev.txt
CARWATCH_API_DB=runtime/api/carwatch.sqlite3 \
CARWATCH_ALLOWED_ORIGINS=http://localhost:8520,http://127.0.0.1:8520 \
server/.venv/bin/python -m uvicorn server.api:create_app --factory --host 127.0.0.1 --port 8518
```

In another terminal, issue a private invitation for that same database:

```sh
server/.venv/bin/python -m server.manage invite --db runtime/api/carwatch.sqlite3
```

The displayed code is a secret. It expires in 24 hours and can be redeemed once. Enter it in the app's **Have an invitation?** form. Environment examples are documentation; the API does not automatically load `.env` files. Health is available at `/health`. All camera/event operations require scoped bearer credentials.

## Pair a station

The station needs the root project's CV dependencies and a USB camera, not the API-only environment. First calibrate the actual view in the local dashboard and save its camera profile. Extract the selected entry from the local `runtime/cameras.json` dictionary into a separate JSON file such as `runtime/driver-profile.json`; its contents must be one `CameraConfig` object, not the whole dictionary. Use the configured data directory if `CARWATCH_DATA_DIR` overrides `runtime/`.

In the native app, **Add a camera → Generate pairing code**. On the station, with the root `.venv` activated:

```sh
python -m server.relay --server http://127.0.0.1:8518 --pair
```

Paste the code into the hidden terminal prompt. Pairing is single-use and expires after ten minutes. **Finish pairing** generates a replacement if you leave the screen. The relay stores a revocable credential in ignored `runtime/station.json` with owner-only permissions.

To run an explicitly supervised session when ready:

```sh
python -m server.relay --server http://127.0.0.1:8518 \
  --profile runtime/driver-profile.json --camera 0 --minutes 2
```

Only the app's **Start monitoring** request opens the camera while this relay is running. The relay checks for pause every two seconds, stops on a server error/disconnection, and ends after 1–10 minutes. A blocked network call can delay stop detection by up to its eight-second timeout; the local monitor also has a time limit. Ctrl+C stops it. Closing the phone app does not stop the station. No unattended background camera service is installed.

Live snapshots are resized and uploaded to the configured API. Originals remain on the station. No continuous video/audio is uploaded. A station's credential can send events only for its paired camera; removing that camera revokes it and deletes its API evidence. The pilot does not connect arbitrary dashcams or provide universal camera compatibility.

## Push configuration

After configuring a native Expo build and its APNs/FCM credentials, set these **server-only** environment variables:

```sh
CARWATCH_PUSH_ENABLED=1
CARWATCH_EXPO_ACCESS_TOKEN=<your-server-side-Expo-access-token>
```

Enable enhanced push security for that Expo project as well. Do not paste access tokens in source or a public command transcript. The app must register its token with this API, and the camera's alert switch must be enabled. Live events are persisted before the worker queues a generic notification with an event reference. Demo events never trigger push; an explicit test button queues a separately labeled test message.

The sender uses fixed verified-HTTPS Expo endpoints, no redirects, a two-minute send window, at most three attempts, and a 30-second cooldown per camera/cue. Transport uncertainty can cause duplicates. Pausing, disabling alerts, or signing out cancels unsent work; already in-flight/provider-accepted messages cannot be recalled. Receipts are polled after 15 minutes, up to 24 hours. Expo/APNs/FCM acknowledgement does not prove display on a phone.

## Operating boundary

For now, use one API worker with local synthetic data. A future hosted pilot needs TLS termination, restricted filesystem access and encrypted disks/backups, configured reverse-proxy timeouts/body limits/rate limiting, credential operations, monitoring, and a reviewed retention process. The in-process rate limiter and SQLite queue are not a distributed service. Never expose the separate Streamlit app as the phone API.

Passwords use salted scrypt; invitations, account sessions and station bearer tokens are stored hashed. Push registration tokens and event images are stored in the database because delivery/review needs them. The database is not application-encrypted and its operator can read it. Limits: five cameras/account, five push installs/account, 1,000 events/camera, newest 100 in the feed. Data remains until camera/account deletion; no automatic retention/export UI or password recovery is supplied. Retained backups require separate deletion. See [security notes](../SECURITY.md).

## Tests

```sh
server/.venv/bin/python -m pytest server/tests -q
server/.venv/bin/python -m pip check
```

Tests use generated images, temporary SQLite databases, fake cameras, and mocked Expo responses. They verify isolation, pairing, cancellation, retry/expiry behavior, request construction, feedback persistence, and relay stop behavior without opening hardware or sending notifications.
