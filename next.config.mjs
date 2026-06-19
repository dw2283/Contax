/** @type {import('next').NextConfig} */
const nextConfig = {
  // Pin the workspace root so Next.js doesn't pick up an unrelated lockfile.
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
