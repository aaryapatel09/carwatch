import { test } from "node:test";
import assert from "node:assert/strict";
import { serverURL, cameraStatus, eventId } from "../src/lib/core.ts";
test("production connections require HTTPS and reject credentials or paths", () => {
  assert.equal(serverURL("https://example.com/", false), "https://example.com");
  for (const url of [
    "http://example.com",
    "https://name:password@example.com",
    "https://example.com/v1",
    "https://example.com?token=value",
  ])
    assert.throws(() => serverURL(url, false));
  assert.equal(
    serverURL("http://127.0.0.1:8518", true),
    "http://127.0.0.1:8518",
  );
  assert.throws(() => serverURL("http://127.0.0.1:8518", false));
});
test("armed does not claim a disconnected camera is monitoring", () => {
  const c = {
    id: "a",
    name: "door",
    armed: 1,
    notify: 1,
    paired: true,
    last_seen: 100,
    capture: "running",
  };
  assert.equal(cameraStatus(c, 110), "Monitoring");
  assert.equal(cameraStatus(c, 150), "Offline");
  assert.equal(cameraStatus({ ...c, armed: 0 }, 110), "Pause requested");
  assert.equal(
    cameraStatus({ ...c, capture: "ready" }, 110),
    "Waiting for camera",
  );
});
test("notification taps accept event IDs, never arbitrary navigation URLs", () => {
  assert.equal(eventId("a".repeat(32)), "a".repeat(32));
  assert.equal(eventId("https://example.com"), null);
  assert.equal(eventId("../secret"), null);
});
