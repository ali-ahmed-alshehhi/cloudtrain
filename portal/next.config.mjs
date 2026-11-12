// "standalone" builds a small server folder, so the Docker image does not need node_modules.
const nextConfig = {
  output: "standalone",
};

export default nextConfig;
