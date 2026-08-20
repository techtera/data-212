import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

/** @type {import("eslint").Linter.FlatConfig[]} */
const eslintConfig = [
  ...nextCoreWebVitals,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "public/mockServiceWorker.js",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;
