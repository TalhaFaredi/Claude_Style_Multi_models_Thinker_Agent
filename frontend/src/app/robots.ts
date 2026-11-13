import type { MetadataRoute } from "next";
import { SITE } from "@/domain/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: ["/", "/terms", "/privacy"], disallow: ["/app", "/account", "/admin", "/api/", "/reset", "/login", "/signup", "/forgot"] },
    sitemap: `${SITE.url}/sitemap.xml`,
  };
}
