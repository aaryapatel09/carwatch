import React, { useState } from "react";
import { router } from "expo-router";
import { useCarwatch } from "../../lib/state";
import { cameraStatus } from "../../lib/core";
import {
  Page,
  Heading,
  Card,
  Label,
  Body,
  Button,
  Notice,
  CarMap,
} from "../../components/ui";
export default function Home() {
  const { cameras, events, demo, error, updateCamera, refresh, refreshing } =
    useCarwatch();
  const [busy, setBusy] = useState(""),
    [message, setMessage] = useState("");
  return (
    <Page>
      <Heading
        eyebrow={
          demo
            ? "Interactive demo · no camera connected"
            : "Carwatch · Your cameras"
        }
        title="Your car, at a glance."
        text={
          demo
            ? "Explore example activity. Nothing here opens a camera or sends a notification."
            : "Monitoring status and the moments worth reviewing."
        }
      />
      <Notice text={message || error} />
      <CarMap demo={demo} />
      {cameras.map((c) => (
        <Card key={c.id}>
          <Label>{c.name}</Label>
          <Body accent>
            {demo ? "Demo · " : ""}
            {cameraStatus(c)}
          </Body>
          <Body>
            {c.paired
              ? "A running camera station is required. Pilot sessions last up to 10 minutes."
              : "Pair a Carwatch camera station to get started."}
          </Body>
          {!c.paired && (
            <Button
              secondary
              title="Finish pairing"
              onPress={() =>
                router.push({ pathname: "/pair", params: { cameraId: c.id } })
              }
            />
          )}
          {c.paired && (
            <Button
              secondary
              title={c.armed ? "Pause monitoring" : "Start monitoring"}
              busy={busy === c.id}
              onPress={() => {
                setBusy(c.id);
                setMessage("");
                void updateCamera(c, !c.armed, Boolean(c.notify))
                  .catch((e) => setMessage(e.message))
                  .finally(() => setBusy(""));
              }}
            />
          )}
        </Card>
      ))}
      {!cameras.length && (
        <Card>
          <Label>Your first camera</Label>
          <Body>
            Add a view and securely pair the computer running your camera.
          </Body>
        </Card>
      )}
      <Button title="Add a camera" onPress={() => router.push("/pair")} />
      <Button
        secondary
        title={`Review activity · ${events.length}`}
        onPress={() => router.push("/(tabs)/activity")}
      />
      {!demo && (
        <Button
          secondary
          title="Refresh status"
          busy={refreshing}
          onPress={() => void refresh()}
        />
      )}
      <Body>
        Camera blind spots and missed detections are possible. No alerts does
        not mean a scene is safe.
      </Body>
    </Page>
  );
}
