import React, { useState } from "react";
import { Text } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useCarwatch } from "../lib/state";
import { Camera } from "../lib/core";
import {
  Page,
  Heading,
  Card,
  Body,
  Button,
  Field,
  Notice,
  C,
} from "../components/ui";
export default function Pair() {
  const { cameraId } = useLocalSearchParams<{ cameraId?: string }>();
  const [createdId, setCreatedId] = useState(cameraId || "");
  const { demo, session, request, refresh } = useCarwatch();
  const [name, setName] = useState("Driver side"),
    [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  if (!demo && !session) return <Redirect href="/" />;
  async function create() {
    setBusy(true);
    setError("");
    try {
      const id =
        createdId ||
        (await request<Camera>("/v1/cameras", "POST", { name })).id;
      setCreatedId(id);
      const p = await request<{ code: string }>(
        "/v1/cameras/" + id + "/pairing",
        "POST",
      );
      setCode(p.code);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pairing unavailable");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Button secondary title="Back to my car" onPress={() => router.back()} />
      <Heading
        eyebrow="A private connection"
        title="Pair your camera station."
        text="For this pilot, your station is a computer running Carwatch with a USB camera. It stays near the car and online."
      />
      <Notice
        text={
          demo
            ? "Demo mode: pairing is available after signing in to a configured server."
            : error
        }
      />
      <Card>
        <Body>1. Name this view.</Body>
        <Body>2. Generate a single-use pairing code.</Body>
        <Body>
          3. Enter it in the Carwatch station terminal. Never share it publicly.
        </Body>
      </Card>
      {!createdId && (
        <Field
          label="Camera name"
          value={name}
          onChangeText={setName}
          autoCapitalize="sentences"
        />
      )}
      {code ? (
        <Card>
          <Text
            selectable
            style={{ color: C.mint, fontSize: 17, fontFamily: "monospace" }}
          >
            {code}
          </Text>
          <Body>
            Expires in 10 minutes. Keep this screen open while pairing. The
            station will appear online after its first heartbeat.
          </Body>
        </Card>
      ) : (
        <Button
          title="Generate pairing code"
          busy={busy}
          disabled={demo || !name.trim()}
          onPress={() => void create()}
        />
      )}
      <Body>
        This does not connect arbitrary dashcams. The pilot uses the camera
        station supplied in the repository.
      </Body>
    </Page>
  );
}
