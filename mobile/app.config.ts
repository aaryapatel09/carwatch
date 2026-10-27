import type { ExpoConfig } from "expo/config";
const config: ExpoConfig = {
  name: "Carwatch",
  slug: "carwatch",
  version: "0.2.0",
  scheme: "carwatch",
  orientation: "portrait",
  userInterfaceStyle: "dark",
  icon: "./assets/carwatch-icon.png",
  ios: {
    supportsTablet: true,
    bundleIdentifier: "site.aaryapatel.carwatch",
    infoPlist: { ITSAppUsesNonExemptEncryption: false },
  },
  android: {
    package: "site.aaryapatel.carwatch",
    ...(process.env.GOOGLE_SERVICES_JSON
      ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON }
      : {}),
    adaptiveIcon: {
      foregroundImage: "./assets/carwatch-icon.png",
      backgroundColor: "#0C1717",
    },
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    ["expo-notifications", { color: "#B5F2CB" }],
  ],
  extra: {
    ...(process.env.EXPO_PUBLIC_EAS_PROJECT_ID
      ? { eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID } }
      : {}),
  },
  web: { bundler: "metro" },
};
export default config;
