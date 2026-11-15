export interface ClothingAttributes {
  clothing_type: string;
  primary_color: string;
  secondary_color: string | null;
  pattern: string;
  style: string;
  /** Confidence of the clothing-type detection (primary signal). */
  confidence: number;
  color_confidence?: number;
  pattern_confidence?: number;
  style_confidence?: number;
  description: string;
  description_relevant: boolean;
  /** Fine colour name from the pixels (e.g. "charcoal" where primary_color says "grey"). */
  color_name?: string | null;
  /** Measured hex of the garment's primary / secondary colour. */
  primary_hex?: string | null;
  secondary_hex?: string | null;
  /** Fine garment or accessory type, e.g. "denim_jacket", "loafers", "belt". */
  garment_type?: string | null;
  garment_type_confidence?: number;
  /** 0 lounge · 1 casual · 2 smart casual · 3 business · 4 black tie (cascade mode only). */
  formality?: number | null;
  /** Visual register, e.g. "minimalist", "ethnic_traditional" (cascade mode only). */
  aesthetic?: string | null;
  /** Upload guard: "degrade" means usable but with a caveat in guard_message. */
  guard?: "pass" | "degrade";
  guard_reason?: string;
  guard_message?: string;
  /** Other items visible in the photo (cascade mode only). */
  other_garments?: string[];
  /** Occasions the garment suits, most probable first (cascade mode only). */
  occasions?: string[];
  /** Calibrated probability of fit per occasion (cascade mode only). */
  occasion_scores?: Record<string, number>;
}

export type Gender = "male" | "female" | "unisex";
export type ShoppingIntent = "menswear" | "womenswear" | "unisex" | "all";

export interface ProductLink {
  title: string;
  price: string;
  link: string;
  thumbnail: string;
  source: string;
  match_score?: number;
  match_reason?: string;
  /** Retrieval facts behind this product — which arm found it, rank, rerank score. */
  match_evidence?: string[];
}

export interface RecommendationItem {
  item_type: string;
  color: string;
  style: string;
  reason: string;
  /** True when the user already owns this item; shopping is skipped for it. */
  owned?: boolean;
  /** Wardrobe item that covers this piece, when matched from the closet. */
  wardrobe_item_id?: string | null;
  products: ProductLink[];
}

export interface Recommendation {
  id: string;
  items: RecommendationItem[];
  overall_explanation: string;
  /** Rule-engine facts this recommendation is grounded in. */
  evidence?: string[];
  style_tags: string[];
  confidence: number;
}

export interface AnalysisResponse {
  request_id: string;
  detected_attributes: ClothingAttributes;
  recommendations: Recommendation[];
  created_at: string;
}

export interface StreamAnalysisResult {
  request_id: string;
  detected_attributes: ClothingAttributes | null;
  recommendations: Recommendation[];
  errors: string[] | null;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface FeedbackRequest {
  request_id: string;
  recommendation_id: string;
  feedback: "like" | "dislike";
  user_id?: string;
  comment?: string;
}

export type SSEEventType =
  | "status"
  | "agent_done"
  | "warning"
  | "error"
  | "result"
  | "done";

export interface SSEEvent {
  event: SSEEventType;
  data: string;
}

export interface SSEStatusData {
  stage: string;
  message: string;
  request_id?: string;
}

export interface SSEResultData {
  request_id: StreamAnalysisResult["request_id"];
  detected_attributes: StreamAnalysisResult["detected_attributes"];
  recommendations: StreamAnalysisResult["recommendations"];
  errors: StreamAnalysisResult["errors"];
}

export interface SSEDoneData {
  elapsed_s: number;
}

export interface WardrobeItem {
  id: string;
  label: string;
  clothing_type: string;
  color: string;
  pattern: string;
  style: string;
  created_at: string | null;
}

export interface WardrobeItemUpdate {
  label?: string;
  clothing_type?: string;
  color?: string;
  pattern?: string;
  style?: string;
}
