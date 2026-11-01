# Maison Muse Android app

The Android app packages the existing React storefront with Capacitor. It does
not request camera or microphone access and does not run hidden background
services. Users can close and uninstall it through normal Android controls.

## Requirements

- Node.js 22 or newer
- Android Studio with Android SDK Platform 36 and Build Tools installed
- JDK 21

## Run the Android project

From `frontend`:

```powershell
npm install
npm run android:sync
npm run android:open
```

The checked-in `android` project was generated with Capacitor. If you create a
fresh project without that folder, generate the platform once with
`npx cap add android` before syncing.

In Android Studio, select an emulator or connected device and run the app. For
subsequent web changes, run `npm run android:sync` before rebuilding the native
app.

## Backend configuration

The app must use a deployed HTTPS API. Set `VITE_API_BASE_URL` to that API's
origin when building, for example:

```powershell
$env:VITE_API_BASE_URL = "https://api.example.com"
npm run android:sync
```

Configure the backend to allow the Capacitor WebView origin (`https://localhost`)
in `CORS_ORIGINS`. Never put admin passwords, session secrets, or payment
credentials in the Android app or its Vite environment variables.

The app currently uses browser-session authentication for its admin area. Verify
admin cookie behavior in the Android WebView and production API deployment
before enabling administrative workflows in a Play Store release.

## Play Store release

Create and sign an Android App Bundle (`.aab`) in Android Studio. Configure a
production application ID, privacy policy, store listing, and data-safety
disclosures before publishing. The app does not collect camera or microphone
data.
