/** @type {import('next').NextConfig} */

// Browser security headers for every page. The API is served by the backend behind the same domain (see Caddyfile).
// 'unsafe-inline' for scripts is needed by Next's own bootstrap scripts; everything else stays on this origin.
const apiOrigin = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'"),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiOrigin}`.trim(),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // A self-contained server for the Docker image (see frontend/Dockerfile). Local `next dev` is unaffected.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  distDir: process.env.NEXT_BUILD_DIR || ".next",
  ...(process.env.MMA_DEMO === "1" ? { env: { NEXT_PUBLIC_API_URL: "" } } : {}),
  async headers() {
    // HSTS only means something over HTTPS and must not be cached against http://localhost during development.
    const list = process.env.NODE_ENV === "production" ? securityHeaders : securityHeaders.filter((h) => h.key !== "Strict-Transport-Security");
    return [{ source: "/:path*", headers: list }];
  },
};
export default nextConfig;
