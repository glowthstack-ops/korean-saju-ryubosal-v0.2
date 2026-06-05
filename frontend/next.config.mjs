/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 프로덕션 빌드(.next-prod)와 개발(.next)을 분리해 캐시 충돌을 방지.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default nextConfig;
