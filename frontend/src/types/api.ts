export interface ClothingAttributes {
  clothing_type: string;
  primary_color: string;
  secondary_color: string | null;
  pattern: string;
  style: string;
  confidence: number;
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
}

export interface RecommendationItem {
  item_type: string;
  color: string;
  style: string;
  reason: string;
  products: ProductLink[];
}

export interface Recommendation {
  id: string;
  items: RecommendationItem[];
  overall_explanation: string;
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
