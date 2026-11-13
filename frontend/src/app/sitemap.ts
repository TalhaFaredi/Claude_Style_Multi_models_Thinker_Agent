import type { MetadataRoute } from "next";
import { SITE } from "@/domain/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/terms", "/privacy"].map((path) => ({ url: `${SITE.url}${path}`, changeFrequency: "monthly", priority: path === "" ? 1 : 0.3 }));
}
