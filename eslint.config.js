import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["web/**/*.js"],
    languageOptions: {
      sourceType: "module",
      // Leaflet loads from a script tag as the global L.
      globals: { ...globals.browser, L: "readonly" },
    },
  },
];
