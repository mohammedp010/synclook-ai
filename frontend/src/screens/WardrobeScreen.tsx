import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useNavigation } from "@react-navigation/native";

import { GlowBackground } from "../components/ui/GlowBackground";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import {
  addWardrobeItem,
  deleteWardrobeItem,
  listWardrobeItems,
  updateWardrobeItem,
} from "../api/endpoints";
import { useAppStore } from "../store/useAppStore";
import { colors, typography, spacing, radius, glass } from "../theme/tokens";
import { fullWidthContent, isWideWeb } from "../utils/responsive";
import type { WardrobeItem } from "../types/api";

const IS_WIDE_LAYOUT = isWideWeb;

interface EditDraft {
  label: string;
  clothing_type: string;
  color: string;
  style: string;
}

export default function WardrobeScreen() {
  const navigation = useNavigation<any>();
  const userId = useAppStore((s) => s.userId) ?? "demo-user";

  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft>({ label: "", clothing_type: "", color: "", style: "" });

  const refresh = useCallback(async () => {
    try {
      setError(null);
      setItems(await listWardrobeItems(userId));
    } catch (e: any) {
      setError(e?.message ?? "Could not load wardrobe");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addItem = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (result.canceled || !result.assets[0]) return;

    setUploading(true);
    try {
      await addWardrobeItem(result.assets[0].uri, userId);
      await refresh();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (e: any) {
      setError(e?.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [userId, refresh]);

  const startEdit = useCallback((item: WardrobeItem) => {
    setEditingId(item.id);
    setDraft({
      label: item.label,
      clothing_type: item.clothing_type,
      color: item.color,
      style: item.style,
    });
  }, []);

  const saveEdit = useCallback(async () => {
    if (!editingId) return;
    try {
      await updateWardrobeItem(editingId, userId, draft);
      setEditingId(null);
      await refresh();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (e: any) {
      setError(e?.message ?? "Update failed");
    }
  }, [editingId, userId, draft, refresh]);

  const removeItem = useCallback(
    async (itemId: string) => {
      try {
        await deleteWardrobeItem(itemId, userId);
        setItems((prev) => prev.filter((i) => i.id !== itemId));
      } catch (e: any) {
        setError(e?.message ?? "Delete failed");
      }
    },
    [userId]
  );

  return (
    <GlowBackground>
      <SafeAreaView style={styles.container}>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <AnimatedEntry index={0}>
            <View style={styles.headerRow}>
              <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                <Text style={styles.backText}>←</Text>
              </TouchableOpacity>
              <Text style={styles.title}>My Wardrobe</Text>
            </View>
            <Text style={styles.subtitle}>
              Garments you add here are auto-tagged by the AI. Recommendations will prefer what you
              already own — shopping only covers the gaps.
            </Text>
          </AnimatedEntry>

          <AnimatedEntry index={1}>
            <TouchableOpacity style={styles.addBtn} onPress={addItem} disabled={uploading} activeOpacity={0.8}>
              {uploading ? (
                <ActivityIndicator color={colors.text.onBrand} />
              ) : (
                <Text style={styles.addBtnText}>＋ Add a garment photo</Text>
              )}
            </TouchableOpacity>
          </AnimatedEntry>

          {error && <Text style={styles.error}>{error}</Text>}

          {loading ? (
            <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brand[400]} />
          ) : items.length === 0 ? (
            <AnimatedEntry index={2}>
              <Text style={styles.empty}>Your closet is empty — add a few garments to unlock “wear what you own”.</Text>
            </AnimatedEntry>
          ) : (
            items.map((item, idx) => (
              <AnimatedEntry key={item.id} index={2 + idx}>
                <View style={styles.itemCard}>
                  {editingId === item.id ? (
                    <View style={styles.editGroup}>
                      {(
                        [
                          ["label", "Label"],
                          ["clothing_type", "Type (e.g. shirt, jeans)"],
                          ["color", "Color"],
                          ["style", "Style"],
                        ] as const
                      ).map(([field, placeholder]) => (
                        <TextInput
                          key={field}
                          style={styles.editInput}
                          value={draft[field]}
                          onChangeText={(v) => setDraft((d) => ({ ...d, [field]: v }))}
                          placeholder={placeholder}
                          placeholderTextColor={colors.text.tertiary}
                          autoCapitalize="none"
                        />
                      ))}
                      <View style={styles.rowEnd}>
                        <TouchableOpacity style={styles.smallBtn} onPress={() => setEditingId(null)}>
                          <Text style={styles.smallBtnText}>Cancel</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.smallBtn, styles.smallBtnPrimary]} onPress={saveEdit}>
                          <Text style={[styles.smallBtnText, styles.smallBtnTextPrimary]}>Save</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : (
                    <>
                      <View style={styles.itemInfo}>
                        <Text style={styles.itemTitle}>
                          {item.label || `${item.color} ${item.clothing_type}`}
                        </Text>
                        <Text style={styles.itemTags}>
                          {item.clothing_type} · {item.color} · {item.style}
                        </Text>
                      </View>
                      <View style={styles.rowEnd}>
                        <TouchableOpacity style={styles.smallBtn} onPress={() => startEdit(item)}>
                          <Text style={styles.smallBtnText}>Fix tags</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.smallBtn} onPress={() => removeItem(item.id)}>
                          <Text style={[styles.smallBtnText, styles.deleteText]}>Remove</Text>
                        </TouchableOpacity>
                      </View>
                    </>
                  )}
                </View>
              </AnimatedEntry>
            ))
          )}
        </ScrollView>
      </SafeAreaView>
    </GlowBackground>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scroll: {
    ...fullWidthContent(),
    paddingHorizontal: IS_WIDE_LAYOUT ? 80 : 24,
    paddingBottom: 64,
    maxWidth: IS_WIDE_LAYOUT ? 720 : undefined,
    alignSelf: "center",
    width: "100%",
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: radius.full,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface.tertiary,
  },
  backText: { color: colors.text.primary, fontSize: 18 },
  title: {
    fontFamily: "SpaceGrotesk_700Bold",
    fontSize: IS_WIDE_LAYOUT ? 32 : 24,
    color: colors.text.primary,
  },
  subtitle: {
    ...typography.body.sm,
    color: colors.text.secondary,
    marginBottom: spacing.lg,
  },
  addBtn: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: spacing.md,
    marginBottom: spacing.lg,
  },
  addBtnText: { ...typography.label.md, color: colors.text.onBrand },
  error: { ...typography.body.sm, color: "#ff8080", marginBottom: spacing.md },
  empty: {
    ...typography.body.md,
    color: colors.text.tertiary,
    textAlign: "center",
    marginTop: spacing.xl,
  },
  itemCard: {
    ...glass.card,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
    flexDirection: IS_WIDE_LAYOUT ? "row" : "column",
    justifyContent: "space-between",
    alignItems: IS_WIDE_LAYOUT ? "center" : "stretch",
    gap: spacing.sm,
  },
  itemInfo: { flexShrink: 1 },
  itemTitle: {
    ...typography.label.md,
    color: colors.text.primary,
    textTransform: "capitalize",
  },
  itemTags: {
    ...typography.body.xs,
    color: colors.text.secondary,
    marginTop: 2,
    textTransform: "capitalize",
  },
  rowEnd: {
    flexDirection: "row",
    gap: spacing.xs,
    justifyContent: "flex-end",
  },
  smallBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.full,
    backgroundColor: colors.surface.tertiary,
  },
  smallBtnPrimary: { backgroundColor: colors.brand[600] },
  smallBtnText: { ...typography.label.sm, color: colors.text.secondary },
  smallBtnTextPrimary: { color: colors.text.onBrand },
  deleteText: { color: "#ff8080" },
  editGroup: { gap: spacing.xs, width: "100%" },
  editInput: {
    ...typography.body.sm,
    color: colors.text.primary,
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
});
