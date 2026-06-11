/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // LLM 통변 호출은 수십 초 걸릴 수 있음 — 프록시 기본 30초 타임아웃 연장.
  experimental: { proxyTimeout: 120_000 },
  // 프로덕션 빌드(.next-prod)와 개발(.next)을 분리해 캐시 충돌을 방지.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // 외부 노출(터널) 시 프론트와 같은 출처로 API를 받기 위해 /api/* 를 백엔드로 프록시.
  // (클라이언트는 상대경로로 호출 → 터널 1개로 동작, CORS 불필요)
  async rewrites() {
    const backend = process.env.SAJU_BACKEND_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default nextConfig;
