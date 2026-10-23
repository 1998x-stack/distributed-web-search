/** Browser requests stay same-origin; Next server proxies only read endpoints. */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/v1/search", destination: "http://api:8000/api/v1/search" },
            { source: "/api/v1/stats", destination: "http://api:8000/api/v1/stats" },
            { source: "/api/v1/cluster", destination: "http://api:8000/api/v1/cluster" },
            { source: "/api/v1/health", destination: "http://api:8000/api/v1/health" }];
  },
};
export default nextConfig;
