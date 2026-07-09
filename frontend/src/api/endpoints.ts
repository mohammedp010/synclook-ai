import { Platform } from "react-native";
import { api } from "./client";
import type {
  AnalysisResponse,
  FeedbackRequest,
  HealthResponse,
  ShoppingIntent,
  WardrobeItem,
  WardrobeItemUpdate,
} from "../types/api";

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await api.get("/health");
  return data;
}

/** Build a FormData with the image correctly for web (Blob) and native (uri object). */
export async function buildImageFormData(imageUri: string): Promise<FormData> {
  const formData = new FormData();
  if (Platform.OS === "web") {
    const response = await fetch(imageUri);
    const blob = await response.blob();
    formData.append("image", blob, "clothing.jpg");
  } else {
    formData.append("image", { uri: imageUri, type: "image/jpeg", name: "clothing.jpg" } as any);
  }
  return formData;
}

export async function analyzeImage(
  imageUri: string,
  userId?: string,
  shoppingIntent: ShoppingIntent = "unisex",
  includeProducts: boolean = true,
  userIntent?: string
): Promise<AnalysisResponse> {
  const formData = await buildImageFormData(imageUri);

  const params: Record<string, string | boolean> = {
    shopping_intent: shoppingIntent,
    include_products: includeProducts,
  };
  if (userId) params.user_id = userId;
  if (userIntent?.trim()) params.user_intent = userIntent.trim();

  const { data } = await api.post("/analyze", formData, {
    params,
    headers: { "Content-Type": "multipart/form-data" },
  });

  return data;
}

export async function submitFeedback(
  feedback: FeedbackRequest
): Promise<void> {
  await api.post("/feedback", feedback);
}

// ── Wardrobe (digital closet) ────────────────────────────────────────

export async function addWardrobeItem(
  imageUri: string,
  userId: string,
  label: string = ""
): Promise<WardrobeItem> {
  const formData = await buildImageFormData(imageUri);
  const { data } = await api.post("/wardrobe/items", formData, {
    params: { user_id: userId, label },
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function listWardrobeItems(userId: string): Promise<WardrobeItem[]> {
  const { data } = await api.get("/wardrobe/items", { params: { user_id: userId } });
  return data;
}

export async function updateWardrobeItem(
  itemId: string,
  userId: string,
  update: WardrobeItemUpdate
): Promise<WardrobeItem> {
  const { data } = await api.patch(`/wardrobe/items/${itemId}`, update, {
    params: { user_id: userId },
  });
  return data;
}

export async function deleteWardrobeItem(itemId: string, userId: string): Promise<void> {
  await api.delete(`/wardrobe/items/${itemId}`, { params: { user_id: userId } });
}
