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
