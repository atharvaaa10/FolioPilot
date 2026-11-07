import tsParser from "@typescript-eslint/parser";

export default [
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    rules: {
      "no-unused-vars": "off",
    },
  },
  {
    files: ["src/app/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    ignores: ["**/*.test.{ts,tsx}", "**/test/**", "**/__tests__/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "NewExpression[callee.name='Date'][arguments.length=0]",
          message:
            "Do not invoke new Date() with no arguments during render (causes SSR/client hydration mismatch). Use query/props timestamp and format with <LocalTime>.",
        },
        {
          selector: "CallExpression[callee.object.name='Date'][callee.property.name='now']",
          message:
            "Do not call Date.now() during render (causes SSR/client hydration mismatch). Use query/props timestamp and format with <LocalTime>.",
        },
        {
          selector: "CallExpression[callee.object.name='Math'][callee.property.name='random']",
          message:
            "Do not call Math.random() during render (causes SSR/client hydration mismatch). Use React.useId() or deterministic seeds.",
        },
        {
          selector:
            "CallExpression[callee.property.name=/^(toLocaleString|toLocaleDateString|toLocaleTimeString)$/][arguments.length=0]",
          message:
            "Do not call toLocale*() with zero arguments during render (server vs client timezone/locale mismatch). Format client-side using <LocalTime> or provide explicit locale and timeZone.",
        },
      ],
    },
  },
];
