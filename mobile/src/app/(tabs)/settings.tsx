import React, { useState } from "react";
import { Alert, Linking, Platform, Switch, View } from "react-native";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { AndroidImportance } from "expo-notifications";
import { router } from "expo-router";
import { useCarwatch } from "../../lib/state";
import {
  Page,
  Heading,
  Card,
  Label,
  Body,
  Button,
  Notice,
  C,
} from "../../components/ui";
export default function Settings() {
  const {
    demo,
    session,
    profile,
    cameras,
    request,
    refresh,
    signOut,
    updateCamera,
  } = useCarwatch();
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : "Something went wrong. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function enable() {
    if (Platform.OS === "web")
      throw new Error(
        "Phone notifications are available in the native iPhone and Android builds.",
      );
    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ||
      Constants.easConfig?.projectId;
    if (!projectId)
      throw new Error(
        "This build has no Expo project configured yet. See the native setup guide.",
      );
    if (Platform.OS === "android")
      await Notifications.setNotificationChannelAsync("carwatch-activity", {
        name: "Carwatch activity",
        importance: AndroidImportance.DEFAULT,
      });
    let permissions = await Notifications.getPermissionsAsync();
    if (permissions.status !== "granted")
      permissions = await Notifications.requestPermissionsAsync();
    if (permissions.status !== "granted")
      throw new Error(
        "Notifications are not permitted. You can change this in your phone settings.",
      );
    const token = (await Notifications.getExpoPushTokenAsync({ projectId }))
      .data;
    await request("/v1/push", "POST", { token });
    await refresh();
    setMessage("Registered. Send a test and confirm it arrives on your phone.");
  }
  async function leave() {
    await signOut();
    router.replace("/");
  }
  function removeAccount() {
    Alert.alert(
      "Delete your account?",
      "This permanently deletes your cameras, events, saved images and notification registrations from this server.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete account",
          style: "destructive",
          onPress: () =>
            void perform(async () => {
              await request("/v1/me", "DELETE");
              try {
                await signOut();
              } catch {
                /* Next authenticated request clears the expired session. */
              }
              router.replace("/");
            }),
        },
      ],
    );
  }
  return (
    <Page>
      <Heading
        eyebrow={demo ? "Demo preferences" : "Your preferences"}
        title="On your terms."
        text="Choose when to monitor and how you hear from Carwatch."
      />
      <Notice text={message} />
      <Card>
        <Label>Phone notifications</Label>
        <Body>
          {demo
            ? "The demo never requests notification permission or sends messages."
            : profile?.push_registered
              ? "This phone is registered. Delivery also depends on phone permissions, connectivity and the push provider."
              : "Enable alerts on this device after your server and native build are configured."}
        </Body>
        {!demo && (
          <Body>
            {profile?.push_configured
              ? "Server delivery is configured."
              : "Server delivery is not configured yet."}
          </Body>
        )}
        <Button
          title={
            profile?.push_registered
              ? "Send a test notification"
              : "Enable phone notifications"
          }
          busy={busy}
          disabled={demo || !profile?.push_configured}
          onPress={() =>
            void perform(
              profile?.push_registered
                ? async () => {
                    await request("/v1/push/test", "POST");
                    setMessage(
                      "Test queued. Check your phone; queueing does not confirm receipt.",
                    );
                  }
                : enable,
            )
          }
        />
        {profile?.push_registered && (
          <Button
            secondary
            title="Disable alerts on this phone"
            busy={busy}
            onPress={() =>
              void perform(async () => {
                await request("/v1/push", "DELETE");
                await refresh();
              })
            }
          />
        )}
        <Button
          secondary
          title="Open phone notification settings"
          disabled={Platform.OS === "web" || demo}
          onPress={() => void Linking.openSettings()}
        />
      </Card>
      {cameras.map((c) => (
        <Card key={c.id}>
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 14,
            }}
          >
            <View style={{ flex: 1 }}>
              <Label>{c.name}</Label>
              <Body>Automatic activity alerts</Body>
            </View>
            <Switch
              accessibilityLabel={"Alerts for " + c.name}
              value={Boolean(c.notify)}
              disabled={busy}
              trackColor={{ false: C.line, true: "#5C997A" }}
              thumbColor={C.mint}
              onValueChange={(value) =>
                void perform(() => updateCamera(c, Boolean(c.armed), value))
              }
            />
          </View>
          {!demo && (
            <Button
              secondary
              title={"Remove " + c.name}
              disabled={busy}
              onPress={() =>
                Alert.alert(
                  "Remove camera?",
                  "This revokes the station and deletes its saved events and images.",
                  [
                    { text: "Cancel", style: "cancel" },
                    {
                      text: "Remove",
                      style: "destructive",
                      onPress: () =>
                        void perform(async () => {
                          await request("/v1/cameras/" + c.id, "DELETE");
                          await refresh();
                        }),
                    },
                  ],
                )
              }
            />
          )}
        </Card>
      ))}
      <Card>
        <Label>
          {demo
            ? "Explore without connecting"
            : "Private account · " + session?.username}
        </Label>
        <Body>
          {demo
            ? "Example events are stored only in this app session."
            : "Your station uploads event snapshots to your server. Push messages contain a generic description and event reference, not images or location."}
        </Body>
        <Body>
          Research pilot. Camera compatibility and real phone delivery need
          field testing. There is no emergency response service.
        </Body>
      </Card>
      <Button
        secondary
        title={demo ? "Exit demo" : "Sign out"}
        busy={busy}
        onPress={() => void perform(leave)}
      />
      {!demo && (
        <Button
          secondary
          title="Delete my account and data"
          disabled={busy}
          onPress={removeAccount}
        />
      )}
    </Page>
  );
}
