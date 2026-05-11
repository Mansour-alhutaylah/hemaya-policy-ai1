// Canonical confidence threshold for "Low Confidence — Human Review Recommended"
// banners and filter logic across the frontend. Scores below this value flag a
// mapping/control as needing human review. Centralised so Explainability,
// MappingReview, AI Insights, and any future consumer agree on the value.
//
// Note: the backend duplicates this constant in main.py for the /api/insights
// endpoint. Keep them in sync; this JS value is the authoritative UI value.
export const CONFIDENCE_THRESHOLD = 0.6;

export const isLowConfidence = (score) =>
  typeof score === 'number' && score < CONFIDENCE_THRESHOLD;

export const confidenceLabel = (score) =>
  isLowConfidence(score) ? 'Low' : 'High';
