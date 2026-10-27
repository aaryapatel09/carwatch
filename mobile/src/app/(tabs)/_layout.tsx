import React from "react";
import { Text } from "react-native";
import { Tabs, Redirect } from "expo-router";
import { useCarwatch } from "../../lib/state";
import { C } from "../../components/ui";
export default function Layout() {
  const { ready, session, demo } = useCarwatch();
  if (!ready) return null;
  if (!session && !demo) return <Redirect href="/" />;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.mint,
        tabBarInactiveTintColor: C.muted,
        tabBarStyle: { backgroundColor: C.bg, borderTopColor: C.line },
        sceneStyle: { backgroundColor: C.bg },
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: "My car",
          tabBarIcon: ({ color }) => (
            <Text style={{ color, fontSize: 24 }}>◎</Text>
          ),
        }}
      />
      <Tabs.Screen
        name="activity"
        options={{
          title: "Activity",
          tabBarIcon: ({ color }) => (
            <Text style={{ color, fontSize: 24 }}>≋</Text>
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarIcon: ({ color }) => (
            <Text style={{ color, fontSize: 24 }}>☷</Text>
          ),
        }}
      />
    </Tabs>
  );
}
