/** @type {import('next').NextConfig} */
const nextConfig = {
  // Pin the workspace root so Next.js doesn't pick up an unrelated lockfile.
  turbopack: {
    root: import.meta.dirname,
  },
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${process.env.CONTAX_API_PROXY_TARGET ?? "http://127.0.0.1:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
