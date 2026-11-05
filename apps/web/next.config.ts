import type { NextConfig } from "next";

const API_BASE = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

/**
 * Xavfsizlik sarlavhalari (audit bo‘lim 7.8 / P2-4).
 * — X-Frame-Options: DENY  → clickjacking himoyasi
 * — Content-Security-Policy  → frame-ancestors 'none' (CSP orqali ham)
 * — Referrer-Policy         → tashqi manbalarga to‘liq URL yuborilmasin
 * — Permissions-Policy      → kamera/mikrofon faqat kerakli kontekstda
 */
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), geolocation=(self), microphone=(self), payment=(), usb=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      "style-src 'self' 'unsafe-inline'",
      // `unsafe-eval` faqat dev-server uchun kerak — production'da
      // Next.js runtime'ga kerak emas.
      "script-src 'self' 'unsafe-inline'" +
        (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
      "connect-src 'self' " + API_BASE,
      "upgrade-insecure-requests",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_BASE}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
