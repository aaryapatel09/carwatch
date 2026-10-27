import React, { useEffect, useState } from "react";
import { Image } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useCarwatch } from "../../lib/state";
import { Activity } from "../../lib/core";
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
export default function Detail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { demo, session, events, request, review } = useCarwatch();
  const [event, setEvent] = useState<Activity | undefined>(
      events.find((e) => e.id === id),
    ),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    if (!demo && session)
      void request<Activity>("/v1/events/" + encodeURIComponent(id))
        .then((e) => {
          if (active) setEvent(e);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [id, demo, session, request]);
  if (!demo && !session) return <Redirect href="/" />;
  async function save(value: string) {
    setBusy(true);
    try {
      await review(id, value);
      setEvent((e) => (e ? { ...e, review: value } : e));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save feedback");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Button
        secondary
        title="Back to activity"
        onPress={() => router.replace("/(tabs)/activity")}
      />
      <Notice text={error} />
      {event ? (
        <>
          <Heading
            eyebrow={
              event.origin === "demo"
                ? "Demonstration · illustrative event"
                : "Recorded observation"
            }
            title={event.title}
            text={
              event.camera_name +
              " · " +
              new Date(event.observed_at * 1000).toLocaleString()
            }
          />
          {event.has_snapshot && session ? (
            <Image
              accessibilityLabel="Saved camera evidence"
              source={{
                uri: session.url + "/v1/events/" + event.id + "/snapshot",
                headers: { Authorization: "Bearer " + session.token },
              }}
              style={{
                width: "100%",
                aspectRatio: 4 / 3,
                borderRadius: 20,
                marginBottom: 20,
              }}
              resizeMode="contain"
            />
          ) : (
            <>
              <CarMap demo={event.origin === "demo"} />
              <Body>
                {event.origin === "demo"
                  ? "Illustration only. No real camera footage is used in the demo."
                  : "No image was attached to this event."}
              </Body>
            </>
          )}
          <Card>
            <Label>What this tells you</Label>
            <Body>
              {event.kind === "hand_near_zone"
                ? "An estimated wrist remained near a selected image region. Physical contact is unconfirmed."
                : event.kind === "lingering"
                  ? "A person track remained in the selected region long enough to meet the configured duration."
                  : "A person track entered the selected region repeatedly."}
            </Body>
            <Body>
              These observations do not establish intent or danger. This pilot
              provides snapshots; continuous video clips are not uploaded.
            </Body>
          </Card>
          {event.delivery?.map((d, i) => (
            <Body key={i}>{d.detail || d.state}</Body>
          ))}
          <Label>Was this useful?</Label>
          {["useful", "ordinary", "unclear"].map((value) => (
            <Button
              key={value}
              secondary={event.review !== value}
              busy={busy}
              title={
                value === "useful"
                  ? "Useful observation"
                  : value === "ordinary"
                    ? "Ordinary activity"
                    : "Unclear / tracking issue"
              }
              onPress={() => void save(value)}
            />
          ))}
        </>
      ) : (
        <Body>
          {error ? "This event could not be loaded." : "Loading observation…"}
        </Body>
      )}
    </Page>
  );
}
