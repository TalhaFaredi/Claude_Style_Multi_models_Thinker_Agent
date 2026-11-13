/** Public facts about this deployment. NEXT_PUBLIC_* values are fixed when the site is built (see DEPLOYMENT.md). */
export const SITE = {
  name: process.env.NEXT_PUBLIC_SITE_NAME || "Multi-Mode Assistant",
  url: (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(/\/$/, ""),
  contact: process.env.NEXT_PUBLIC_CONTACT_EMAIL || "",
  operator: process.env.NEXT_PUBLIC_OPERATOR_NAME || "",
  /** Set to 1 once a lawyer has reviewed the Terms and Privacy pages; until then they carry a visible template notice. */
  legalReviewed: process.env.NEXT_PUBLIC_LEGAL_REVIEWED === "1",
};
