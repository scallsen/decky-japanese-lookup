import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "refs", ".claude"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // the classic hook rules only — the preset's React Compiler rules
      // (purity, set-state-in-effect, …) assume a compiler this build lacks
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Steam/Decky internals (window.appStore, DeckyPluginLoader, settings
      // blobs) are untyped; `any` at those boundaries is deliberate.
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
