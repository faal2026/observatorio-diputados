import type { NextConfig } from "next";

// GitHub Pages sirve este proyecto bajo /observatorio-diputados. Al conectar
// el subdominio propio, la variable PAGES_BASE_PATH se configura como "."
// para publicar desde la raíz del dominio.
const configuredBasePath = process.env.PAGES_BASE_PATH ?? "";
const basePath = configuredBasePath === "." ? "" : configuredBasePath.replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  assetPrefix: basePath || undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
