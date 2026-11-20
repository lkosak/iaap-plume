import type { NextConfig } from "next";

// Set NEXT_PUBLIC_BASE_PATH=/iaap-plume for https://lkosak.github.io/iaap-plume/
// Leave it unset for local dev and for hosts that serve the export at /.
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
};

export default nextConfig;
