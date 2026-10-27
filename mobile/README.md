# Carwatch for iPhone and Android

A React Native / Expo 58 companion with private sign-in, camera pairing, monitoring controls, an activity feed, snapshot review, feedback, and notification registration. The offline demo uses illustrations and example events. It never opens a camera or sends notifications.

**Local prototype:** iOS and Android JavaScript bundles compile. Signed native binaries, target-phone notification delivery, and camera field performance have not been verified. This is not an App Store or Play Store release.

## Try it locally

Use Node 24 and npm. From this directory:

```sh
npm ci
npm run web -- --localhost --port 8520
```

Open [localhost:8520](http://localhost:8520) and choose **Explore the demo**. This browser preview uses the same React Native components; browser execution does not verify native behavior. Phone push is only implemented for the native builds.

For a local account, first start the [API](../server/README.md). Then start this app with:

```sh
EXPO_PUBLIC_API_URL=http://127.0.0.1:8518 npm run web -- --localhost --port 8520
```

Choose **Sign in → Have an invitation?**, enter the API operator's single-use invitation and a new username/password (12–128 characters). Development permits HTTP only for loopback, including Android emulator host `10.0.2.2`. Release builds require HTTPS. A physical phone cannot reach your computer through `127.0.0.1`; physical testing needs a reachable HTTPS API.

## Native development builds

With Xcode / CocoaPods or Android Studio / SDK configured:

```sh
npm run ios
npm run android
```

These commands generate native projects from `app.config.ts` and install a development build. Do not edit generated `ios/` or `android/` sources. Use a development build for notifications; Expo Go is not this app's delivery test environment. Allow substantial free disk space for native toolchains and builds.

The checked-in bundle/application ID is `site.aaryapatel.carwatch`. Confirm ownership before distribution. No developer account, EAS project, Firebase project, signing certificate, or hosted API is included.

## Enable real push later

1. Sign into your own Expo account, link this project with `npx eas-cli@latest init`, and configure `EXPO_PUBLIC_EAS_PROJECT_ID` from that project in your local/build environment. These public environment values are bundled into the app; never place secrets in them.
2. Configure the intended API HTTPS origin as `EXPO_PUBLIC_API_URL`.
3. Configure APNs credentials for iOS and FCM v1 credentials for Android using Expo's [push setup guide](https://docs.expo.dev/push-notifications/push-notifications-setup/). Set `GOOGLE_SERVICES_JSON` to the local/build-environment path for your Android `google-services.json`. It is ignored by Git. A Firebase service-account private key belongs in the credential service, never in the app bundle.
4. Enable enhanced push security on the Expo project. Give the API a server-only Expo access token and enable its sender as described in the API guide.
5. Build with `npx eas-cli@latest build --platform ios --profile development` or `--platform android`. EAS account setup, signing, service usage, and platform distribution requirements are separate steps. No remote build is started by this repository.
6. In the installed app, sign in and choose **Settings → Enable phone notifications**. Permission is requested only after this action. Send a test and verify it appears on the target phone, then test a permissioned camera event. Test locked/background states, denied permissions, disconnection, pause, logout, and token replacement.

Provider tickets/receipts are shown as provider status, never as proof a phone displayed an alert. Delivery may be delayed, duplicated, or absent. Notification taps open a private event only after authentication.

## Data and controls

- Native sessions use Expo SecureStore; the browser preview keeps sign-in only in memory. Sessions expire after 30 days. Signing out requires a server connection to revoke that session and its push registration.
- The phone has no camera or microphone capture feature. A separately started computer station performs CV and uploads snapshots to the configured API.
- Camera heartbeat status distinguishes offline, paused, starting, and monitoring. An armed camera without a recent heartbeat is shown as offline.
- Feedback is saved for review; it does not retrain or improve a model automatically.
- Delete account / remove camera are destructive native confirmation flows. They delete API records, not the station's original local recordings or operator backups. No cloud backup lifecycle is supplied.

## Verify

```sh
npm run typecheck
npm run lint
npm test
npm run export
```

See [the native verification record](../docs/NATIVE-VERIFICATION.md) for current limits and upstream dependency advisories. Own project code follows the root AGPL-3.0 license. The Expo starter's MIT notice is retained in `TEMPLATE-LICENSE`.
