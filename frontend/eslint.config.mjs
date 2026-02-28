import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
    baseDirectory: __dirname,
});

const eslintConfig = [
    // Bypassing next/core-web-vitals in ESLint 9 flat config temporarily 
    // to prevent 'circular structure' crashes in IDE plugins. 
    // 'next lint' relies on its internal resolution.
];

export default eslintConfig;
