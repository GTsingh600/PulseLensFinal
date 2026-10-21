import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**", "**/dist/**", ".venv*/**", "data/**", "models/**",
      "**/test-results/**", "playwright-report/**", "server/**", "eval/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // CLAUDE.md rule 1: one clock. Date.now() never goes into timing maths on the client.
      "no-restricted-properties": ["error", {
        object: "Date", property: "now",
        message: "Use now() from @pulselens/capture (performance.now() domain), never Date.now().",
      }],
    },
  },
  {
    files: ["*.config.{js,ts}", "**/vite.config.ts", "e2e/**", "scripts/**/*.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
);
