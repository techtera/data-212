/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['192.168.0.105', '10.152.238.15'],
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'storage.googleapis.com',
        pathname: '/terafac-datasets/**',
      },
    ],
  },
};
 
export default nextConfig; 