// ESLint Configuration — Phase 4E
// Enforces format library usage and code quality rules

module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh', 'custom-rules'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    // Custom rule: prefer format library over toFixed
    'no-restricted-syntax': [
      'error',
      {
        selector: 'CallExpression[callee.property.name="toFixed"]',
        message: 'Use format library (fmtPrice, fmtChange, fmtRate) instead of toFixed()',
      },
    ],
    // Enforce no direct number formatting
    'no-restricted-properties': [
      'error',
      {
        object: 'Number',
        property: 'toFixed',
        message: 'Use format library instead',
      },
      {
        object: 'Number',
        property: 'toPrecision',
        message: 'Use format library instead',
      },
    ],
    // TypeScript specific rules
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/prefer-optional-chain': 'error',
    '@typescript-eslint/prefer-nullish-coalescing': 'error',
    // Import organization
    'sort-imports': [
      'error',
      {
        ignoreDeclarationSort: true,
        memberSyntaxSortOrder: ['none', 'all', 'multiple', 'single'],
      },
    ],
    // React hooks
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    // General code quality
    'eqeqeq': ['error', 'always'],
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'prefer-const': 'error',
    'no-var': 'error',
  },
  overrides: [
    {
      files: ['**/*.test.ts', '**/*.test.tsx'],
      rules: {
        'no-console': 'off',
      },
    },
  ],
};
