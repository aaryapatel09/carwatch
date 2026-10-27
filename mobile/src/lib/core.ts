export type Camera = {
  id: string;
  name: string;
  armed: number;
  notify: number;
  paired: boolean;
  last_seen: number | null;
  capture: string;
};
export type Activity = {
  id: string;
  camera_id: string;
  camera_name: string;
  kind: string;
  observed_at: number;
  title: string;
  origin: string;
  review: string;
  has_snapshot: boolean;
  delivery?: { state: string; detail: string }[];
};
export type Session = { url: string; token: string; username: string };
export function serverURL(value: string, development: boolean): string {
  const u = new URL(value.trim());
  const local = ["127.0.0.1", "localhost", "10.0.2.2"].includes(u.hostname);
  if (
    u.username ||
    u.password ||
    u.search ||
    u.hash ||
    !["", "/"].includes(u.pathname) ||
    (u.protocol !== "https:" &&
      !(development && local && u.protocol === "http:"))
  )
    throw new Error(
      "Use an HTTPS server address without a path or credentials.",
    );
  return u.origin;
}
export function cameraStatus(c: Camera, now = Date.now() / 1000): string {
  if (!c.paired) return "Pairing needed";
  if (!c.last_seen || now - c.last_seen > 45) return "Offline";
  if (c.capture === "error") return "Camera needs attention";
  if (c.capture === "running")
    return c.armed ? "Monitoring" : "Pause requested";
  return c.armed ? "Waiting for camera" : "Paused";
}
export function eventId(value: unknown): string | null {
  return typeof value === "string" && /^[a-f0-9]{32}$/.test(value)
    ? value
    : null;
}
