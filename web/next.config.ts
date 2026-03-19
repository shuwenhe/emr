import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  // Keep local route handlers in src/app/api/** authoritative.
  // Only rewrite API paths that do not have dedicated handlers.
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path((?!reports(?:/|$)|patients(?:/|$)).*)",
        destination: `${apiUrl}/:path`,
      },
    ];
  },
};

export default nextConfig;
