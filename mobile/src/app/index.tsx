import React, { useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { Redirect, router } from "expo-router";
import { useCarwatch } from "../lib/state";
import { serverURL } from "../lib/core";
import {
  Page,
  Heading,
  Body,
  Button,
  Field,
  Notice,
  CarMap,
  C,
} from "../components/ui";
export default function Welcome() {
  const { ready, session, demo, enterDemo, signIn } = useCarwatch();
  const [form, setForm] = useState(false),
    [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [url, setURL] = useState(process.env.EXPO_PUBLIC_API_URL || ""),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [invite, setInvite] = useState("");
  if (!ready)
    return (
      <Page>
        <ActivityIndicator color={C.mint} />
      </Page>
    );
  if (session || demo) return <Redirect href="/(tabs)/home" />;
  async function submit() {
    setBusy(true);
    setError("");
    try {
      const base = serverURL(url, __DEV__);
      const response = await fetch(
        base + "/v1/auth/" + (register ? "register" : "login"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: username.trim(),
            password,
            ...(register ? { invite: invite.trim() } : {}),
          }),
          signal: AbortSignal.timeout(12000),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Please check your details.",
        );
      await signIn({ ...data, url: base });
      setPassword("");
      router.replace("/(tabs)/home");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Text
        style={{
          color: C.mint,
          fontWeight: "700",
          fontSize: 21,
          marginVertical: 24,
        }}
      >
        ◉ carwatch
      </Text>
      {!form ? (
        <>
          <Heading
            eyebrow="Your car. Within reach."
            title={"Step away.\nStay in the loop."}
            text="Activity from your connected camera, delivered to your phone."
          />
          <CarMap />
          <View style={{ gap: 12, marginBottom: 24 }}>
            <Body>01 Connect your camera station</Body>
            <Body>02 Choose when to monitor</Body>
            <Body>03 Get alerts. Review the evidence.</Body>
          </View>
          <Button title="Sign in to Carwatch" onPress={() => setForm(true)} />
          <Button
            secondary
            title="Explore the demo"
            onPress={() => {
              enterDemo();
              router.replace("/(tabs)/home");
            }}
          />
          <Body>
            Private pilot · A camera station stays with your car. This app is
            your companion.
          </Body>
        </>
      ) : (
        <>
          <Heading
            title={register ? "Join the pilot." : "Welcome back."}
            text="Connect to your Carwatch server. Your camera feed stays private to your account."
          />
          <Notice text={error} />
          <Field
            label="Server address"
            placeholder="https://carwatch.example.com"
            value={url}
            onChangeText={setURL}
            keyboardType="url"
            autoCorrect={false}
          />
          <Field
            label="Username"
            value={username}
            onChangeText={setUsername}
            autoCorrect={false}
          />
          <Field
            label="Password"
            placeholder="At least 12 characters"
            secureTextEntry
            value={password}
            onChangeText={setPassword}
            autoComplete={register ? "new-password" : "current-password"}
          />
          {register && (
            <Field
              label="Pilot invitation"
              value={invite}
              onChangeText={setInvite}
              autoCorrect={false}
            />
          )}
          <Button
            title={register ? "Create private account" : "Sign in"}
            busy={busy}
            onPress={() => void submit()}
          />
          <Button
            secondary
            title={
              register
                ? "Already have an account? Sign in"
                : "Have an invitation? Create an account"
            }
            onPress={() => setRegister(!register)}
          />
          <Button secondary title="Back" onPress={() => setForm(false)} />
        </>
      )}
    </Page>
  );
}
