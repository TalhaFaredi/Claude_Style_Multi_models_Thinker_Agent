/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_BUILD_DIR || ".next",
  ...(process.env.MMA_DEMO === "1" ? { env: { NEXT_PUBLIC_API_URL: "" } } : {}),
};
export default nextConfig;
