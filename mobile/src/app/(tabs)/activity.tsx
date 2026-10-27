import React from "react";
import { Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { useCarwatch } from "../../lib/state";
import {
  Page,
  Heading,
  Card,
  Label,
  Body,
  Notice,
  Button,
  C,
} from "../../components/ui";
export default function ActivityScreen() {
  const { events, demo, error, refresh, refreshing } = useCarwatch();
  return (
    <Page>
      <Heading
        eyebrow={demo ? "Example events" : "Private activity feed"}
        title="The moments in between."
        text="Open an observation to review its evidence and leave feedback."
      />
      <Notice text={error} />
      {events.map((e) => (
        <Pressable
          key={e.id}
          accessibilityRole="button"
          accessibilityLabel={"Review " + e.title}
          onPress={() =>
            router.push({ pathname: "/event/[id]", params: { id: e.id } })
          }
        >
          <Card>
            <View
              style={{ flexDirection: "row", justifyContent: "space-between" }}
            >
              <Text style={{ color: C.amber, fontSize: 11, letterSpacing: 1 }}>
                {e.origin === "demo" ? "DEMO EVENT" : "OBSERVATION"}
              </Text>
              <Text style={{ color: C.muted, fontSize: 12 }}>
                {new Date(e.observed_at * 1000).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </Text>
            </View>
            <Label>{e.title}</Label>
            <Body>{e.camera_name} →</Body>
            <Text style={{ color: C.muted, fontSize: 12 }}>
              {e.review === "unreviewed"
                ? "Ready for review"
                : "Reviewed · " + e.review}
            </Text>
          </Card>
        </Pressable>
      ))}
      {!events.length && (
        <Card>
          <Label>No activity recorded yet</Label>
          <Body>
            Once your paired camera is monitoring, saved observations will
            appear here. An empty feed is not a safety assessment.
          </Body>
        </Card>
      )}
      {!demo && (
        <Button
          secondary
          title="Refresh activity"
          busy={refreshing}
          onPress={() => void refresh()}
        />
      )}
    </Page>
  );
}
