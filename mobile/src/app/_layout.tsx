import React, { useEffect } from "react";
import { Platform } from "react-native";
import { Stack, router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as Notifications from "expo-notifications";
import { Provider, useCarwatch } from "../lib/state";
import { eventId } from "../lib/core";
import { C } from "../components/ui";

if (Platform.OS !== "web")
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
function NotificationRoutes() {
  const { session, refresh } = useCarwatch();
  useEffect(() => {
    if (!session || Platform.OS === "web") return;
    let active = true;
    const open = (r: Notifications.NotificationResponse | null) => {
      const id = eventId(r?.notification.request.content.data?.eventId);
      if (id && active)
        router.push({ pathname: "/event/[id]", params: { id } });
    };
    void Notifications.getLastNotificationResponseAsync()
      .then(open)
      .catch(() => {});
    const tapped = Notifications.addNotificationResponseReceivedListener(open);
    const received = Notifications.addNotificationReceivedListener(() => {
      void refresh();
    });
    return () => {
      active = false;
      tapped.remove();
      received.remove();
    };
  }, [session, refresh]);
  return null;
}
export default function Layout() {
  return (
    <Provider>
      <StatusBar style="light" />
      <NotificationRoutes />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: C.bg },
        }}
      />
    </Provider>
  );
}
