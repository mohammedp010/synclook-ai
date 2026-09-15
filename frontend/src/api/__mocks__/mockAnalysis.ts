import type { AnalysisResponse } from "../../types/api";

export const MOCK_ANALYSIS: AnalysisResponse = {
  request_id: "mock-123",
  detected_attributes: {
    clothing_type: "t-shirt",
    primary_color: "navy",
    secondary_color: null,
    pattern: "solid",
    style: "casual",
    confidence: 0.87,
    description: "A navy solid casual t-shirt",
    description_relevant: true,
  },
  recommendations: [
    {
      id: "rec-1",
      items: [
        {
          item_type: "jeans",
          color: "white",
          style: "casual",
          reason: "White jeans create a clean contrast with navy.",
          products: [
            {
              title: "Levi's 511 Slim Fit White Jeans",
              price: "₹2,999",
              link: "https://www.myntra.com/jeans/levis/511-slim-fit",
              thumbnail: "https://assets.myntassets.com/sample-jeans.jpg",
              source: "Myntra",
              match_score: 0.87,
              match_reason:
                "hybrid retrieval; cross-encoder relevance 0.87",
              match_evidence: [
                "Keyword search ranked it #2",
                "Vector search ranked it #1",
                "Both retrieval arms agreed on it",
                "Cross-encoder relevance 0.87",
              ],
            },
          ],
        },
        {
          item_type: "sneakers",
          color: "white",
          style: "casual",
          reason: "White sneakers keep the look fresh and relaxed.",
          products: [
            {
              title: "Nike Air Force 1 White Sneakers",
              price: "₹7,495",
              link: "https://www.amazon.in/nike-air-force-1",
              thumbnail: "https://m.media-amazon.com/sample-nike.jpg",
              source: "Amazon.in",
              match_score: 0.74,
              match_reason:
                "zero-shot gates passed; title similarity 0.71; thumbnail agrees (0.82)",
              match_evidence: [
                "zero-shot gates passed",
                "title similarity 0.71",
                "thumbnail agrees (0.82)",
              ],
            },
          ],
        },
      ],
      overall_explanation:
        "A classic navy and white combination that is timeless and versatile.",
      style_tags: ["casual", "classic", "clean"],
      confidence: 0.92,
    },
    {
      id: "rec-2",
      items: [
        {
          item_type: "chinos",
          color: "beige",
          style: "smart_casual",
          reason: "Beige chinos elevate the navy t-shirt effortlessly.",
          products: [
            {
              title: "H&M Slim Fit Chinos Beige",
              price: "₹1,799",
              link: "https://www2.hm.com/en_in/slim-chinos",
              thumbnail: "https://lp2.hm.com/sample-chinos.jpg",
              source: "H&M",
            },
          ],
        },
        {
          item_type: "loafers",
          color: "brown",
          style: "smart_casual",
          reason: "Brown loafers add warmth and sophistication.",
          products: [
            {
              title: "Clarks Brown Leather Loafers",
              price: "₹4,299",
              link: "https://www.myntra.com/loafers/clarks",
              thumbnail: "https://assets.myntassets.com/sample-loafers.jpg",
              source: "Myntra",
            },
          ],
        },
      ],
      overall_explanation:
        "A smart casual look perfect for a relaxed day out or casual Friday.",
      style_tags: ["smart_casual", "elevated", "warm"],
      confidence: 0.85,
    },
  ],
  created_at: new Date().toISOString(),
};
