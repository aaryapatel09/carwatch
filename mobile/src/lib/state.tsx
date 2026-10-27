import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AppState, Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { Activity, Camera, Session } from "./core";

const KEY = "carwatch.session.v1";
const now = Date.now() / 1000;
const DEMO_CAMERAS: Camera[] = [
  {
    id: "demo-door",
    name: "Driver’s side",
    armed: 0,
    notify: 0,
    paired: true,
    last_seen: now,
    capture: "stopped",
  },
  {
    id: "demo-rear",
    name: "Rear view",
    armed: 0,
    notify: 0,
    paired: false,
    last_seen: null,
    capture: "offline",
  },
];
const DEMO_EVENTS: Activity[] = [
  {
    id: "demo-1",
    camera_id: "demo-door",
    camera_name: "Driver’s side",
    kind: "hand_near_zone",
    title: "Hand near selected region",
    observed_at: now - 420,
    origin: "demo",
    review: "unreviewed",
    has_snapshot: false,
  },
  {
    id: "demo-2",
    camera_id: "demo-door",
    camera_name: "Driver’s side",
    kind: "lingering",
    title: "Sustained presence",
    observed_at: now - 1840,
    origin: "demo",
    review: "unreviewed",
    has_snapshot: false,
  },
  {
    id: "demo-3",
    camera_id: "demo-door",
    camera_name: "Driver’s side",
    kind: "repeated_approach",
    title: "Repeated entry",
    observed_at: now - 4000,
    origin: "demo",
    review: "ordinary",
    has_snapshot: false,
  },
];

type Profile = {
  username: string;
  push_configured: boolean;
  push_registered: boolean;
};
type State = {
  ready: boolean;
  demo: boolean;
  session: Session | null;
  cameras: Camera[];
  events: Activity[];
  profile: Profile | null;
  error: string;
  refreshing: boolean;
  enterDemo: () => void;
  signIn: (s: Session) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  request: <T>(path: string, method?: string, body?: unknown) => Promise<T>;
  updateCamera: (c: Camera, armed: boolean, notify: boolean) => Promise<void>;
  review: (id: string, value: string) => Promise<void>;
};
const Context = createContext<State | null>(null);
export function Provider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false),
    [demo, setDemo] = useState(false),
    [session, setSession] = useState<Session | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]),
    [events, setEvents] = useState<Activity[]>([]),
    [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState(""),
    [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        if (Platform.OS !== "web") {
          const raw = await SecureStore.getItemAsync(KEY);
          if (raw && active) setSession(JSON.parse(raw));
        }
      } catch {
        if (active) setError("Saved sign-in could not be restored.");
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => {
      active = false;
    };
  }, []);
  const clear = useCallback(async () => {
    generation.current++;
    setSession(null);
    setDemo(false);
    setCameras([]);
    setEvents([]);
    setProfile(null);
    setError("");
    setRefreshing(false);
    if (Platform.OS !== "web") await SecureStore.deleteItemAsync(KEY);
  }, []);
  const request = useCallback(
    async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
      if (!session) throw new Error("Sign in to connect to your server.");
      const response = await fetch(session.url + path, {
        method,
        headers: {
          Authorization: "Bearer " + session.token,
          "Content-Type": "application/json",
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: AbortSignal.timeout(12000),
      });
      const data = await response.json();
      if (response.status === 401) {
        await clear();
        throw new Error("Your session expired. Sign in again.");
      }
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Request failed. Try again.",
        );
      return data as T;
    },
    [session, clear],
  );
  const refresh = useCallback(async () => {
    if (!session || demo) return;
    const current = generation.current;
    setRefreshing(true);
    try {
      const [cs, es, me] = await Promise.all([
        request<Camera[]>("/v1/cameras"),
        request<Activity[]>("/v1/events"),
        request<Profile>("/v1/me"),
      ]);
      if (current === generation.current) {
        setCameras(cs);
        setEvents(es);
        setProfile(me);
        setError("");
      }
    } catch (e) {
      if (current === generation.current)
        setError(e instanceof Error ? e.message : "Connection unavailable");
    } finally {
      if (current === generation.current) setRefreshing(false);
    }
  }, [session, demo, request]);
  useEffect(() => {
    const initial = setTimeout(() => {
      void refresh();
    }, 0);
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void refresh();
    }, 15000);
    const sub = AppState.addEventListener("change", (s) => {
      if (s === "active") void refresh();
    });
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      sub.remove();
    };
  }, [refresh]);
  async function signIn(s: Session) {
    if (Platform.OS !== "web")
      await SecureStore.setItemAsync(KEY, JSON.stringify(s));
    generation.current++;
    setDemo(false);
    setSession(s);
    setError("");
  }
  async function signOut() {
    if (session) await request("/v1/auth/logout", "POST");
    await clear();
  }
  async function updateCamera(c: Camera, armed: boolean, notify: boolean) {
    if (demo) {
      setCameras((old) =>
        old.map((x) =>
          x.id === c.id
            ? {
                ...x,
                armed: Number(armed),
                notify: Number(notify),
                capture: armed ? "running" : "stopped",
                last_seen: Date.now() / 1000,
              }
            : x,
        ),
      );
      return;
    }
    await request("/v1/cameras/" + c.id, "PATCH", { armed, notify });
    await refresh();
  }
  async function review(id: string, value: string) {
    if (!demo)
      await request("/v1/events/" + id + "/review", "POST", { review: value });
    setEvents((old) =>
      old.map((e) => (e.id === id ? { ...e, review: value } : e)),
    );
  }
  function enterDemo() {
    generation.current++;
    setSession(null);
    setDemo(true);
    setCameras(
      DEMO_CAMERAS.map((c) => ({
        ...c,
        last_seen: c.paired ? Date.now() / 1000 : null,
      })),
    );
    setEvents(DEMO_EVENTS);
    setError("");
  }
  return (
    <Context.Provider
      value={{
        ready,
        demo,
        session,
        cameras,
        events,
        profile,
        error,
        refreshing,
        enterDemo,
        signIn,
        signOut,
        refresh,
        request,
        updateCamera,
        review,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useCarwatch() {
  const state = useContext(Context);
  if (!state) throw new Error("Missing Carwatch provider");
  return state;
}
