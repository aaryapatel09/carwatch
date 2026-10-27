import React from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
export const C = {
  bg: "#0C1717",
  panel: "#152626",
  line: "#2B4140",
  text: "#F0F5ED",
  muted: "#A1B8B0",
  mint: "#B5F2CB",
  amber: "#F1C78E",
};
export function Page({ children }: { children: React.ReactNode }) {
  return (
    <SafeAreaView style={s.safe} edges={["top", "left", "right"]}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={s.page}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
export function Heading({
  eyebrow,
  title,
  text,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
}) {
  return (
    <View style={{ gap: 10, marginBottom: 24 }}>
      {eyebrow && <Text style={s.eyebrow}>{eyebrow.toUpperCase()}</Text>}
      <Text style={s.title}>{title}</Text>
      {text && <Text style={s.body}>{text}</Text>}
    </View>
  );
}
export function Card({ children }: { children: React.ReactNode }) {
  return <View style={s.card}>{children}</View>;
}
export function Body({
  children,
  accent = false,
}: {
  children: React.ReactNode;
  accent?: boolean;
}) {
  return <Text style={[s.body, accent && { color: C.mint }]}>{children}</Text>;
}
export function Label({ children }: { children: React.ReactNode }) {
  return <Text style={s.label}>{children}</Text>;
}
export function Button({
  title,
  onPress,
  secondary = false,
  busy = false,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.secondary,
        (disabled || busy) && { opacity: 0.45 },
        pressed && { opacity: 0.75 },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={secondary ? C.text : C.bg} />
      ) : (
        <Text style={[s.buttonText, secondary && { color: C.text }]}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ gap: 8, marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor="#78918A"
        style={s.input}
        autoCapitalize="none"
        {...props}
      />
    </View>
  );
}
export function Notice({ text }: { text: string }) {
  return text ? (
    <View accessibilityRole="alert" style={s.notice}>
      <Text style={{ color: C.amber, lineHeight: 21 }}>{text}</Text>
    </View>
  ) : null;
}
export function CarMap({ demo = false }: { demo?: boolean }) {
  return (
    <LinearGradient
      colors={["#244A40", "#132C2C"]}
      style={s.map}
      accessibilityLabel="Illustrated top view of a parked car, not a live camera feed"
    >
      <View style={s.orbit} />
      <View style={[s.orbit, { width: 156, height: 180 }]} />
      <View style={s.car}>
        <View style={s.windshield} />
        <View style={s.roof} />
        <View style={[s.windshield, { height: 17 }]} />
      </View>
      <View style={s.dot} />
      <Text style={s.mapText}>
        {demo ? "ILLUSTRATION · DEMO" : "YOUR CAMERA VIEWS"}
      </Text>
    </LinearGradient>
  );
}
export const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  page: {
    padding: 24,
    paddingBottom: 40,
    maxWidth: 620,
    width: "100%",
    alignSelf: "center",
  },
  eyebrow: {
    color: C.mint,
    fontSize: 11,
    letterSpacing: 2.4,
    fontWeight: "700",
  },
  title: {
    color: C.text,
    fontSize: 38,
    letterSpacing: -1.6,
    lineHeight: 43,
    fontWeight: "700",
  },
  body: { color: C.muted, fontSize: 15, lineHeight: 23 },
  label: { color: C.text, fontSize: 16, fontWeight: "600" },
  card: {
    padding: 20,
    backgroundColor: C.panel,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 22,
    gap: 12,
    marginBottom: 14,
  },
  button: {
    borderRadius: 16,
    padding: 16,
    backgroundColor: C.mint,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 54,
    marginVertical: 6,
  },
  buttonText: { color: C.bg, fontSize: 15, fontWeight: "700" },
  secondary: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: C.line,
  },
  input: {
    color: C.text,
    borderColor: C.line,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 15,
    borderRadius: 14,
    fontSize: 16,
    backgroundColor: C.panel,
  },
  notice: {
    borderLeftWidth: 3,
    borderLeftColor: C.amber,
    backgroundColor: "#302C21",
    padding: 14,
    borderRadius: 8,
    marginBottom: 18,
  },
  map: {
    height: 220,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
    overflow: "hidden",
  },
  orbit: {
    position: "absolute",
    width: 240,
    height: 240,
    borderRadius: 120,
    borderColor: "#44695D",
    borderWidth: 1,
  },
  car: {
    width: 69,
    height: 139,
    borderRadius: 27,
    backgroundColor: "#D5E3D7",
    padding: 7,
    alignItems: "center",
    justifyContent: "space-evenly",
    borderWidth: 2,
    borderColor: "#F0F5ED",
  },
  windshield: {
    width: 48,
    height: 27,
    backgroundColor: "#274B45",
    borderRadius: 9,
  },
  roof: { width: 48, height: 46, borderRadius: 11, backgroundColor: "#A2BCAD" },
  dot: {
    position: "absolute",
    left: "27%",
    top: "47%",
    width: 13,
    height: 13,
    borderRadius: 7,
    backgroundColor: C.mint,
    borderWidth: 3,
    borderColor: "#5C8F74",
  },
  mapText: {
    position: "absolute",
    bottom: 12,
    fontSize: 9,
    color: "#ADCAB8",
    letterSpacing: 2,
  },
});
