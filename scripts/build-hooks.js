#!/usr/bin/env node
/**
 * Bundle GSD-VGL hooks with dependencies for zero-config installation.
 *
 * sql.js includes a WASM binary that must be inlined for portability.
 * This script bundles hooks into self-contained files that work from any cwd.
 */

const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const HOOKS_DIR = path.join(__dirname, '..', 'hooks');
const DIST_DIR = path.join(HOOKS_DIR, 'dist');

// Hooks that need bundling (have npm dependencies)
const HOOKS_TO_BUNDLE = [
  'intel-index.js'
];

async function build() {
  // Ensure dist directory exists
  if (!fs.existsSync(DIST_DIR)) {
    fs.mkdirSync(DIST_DIR, { recursive: true });
  }

  // Bundle hooks with dependencies
  for (const hook of HOOKS_TO_BUNDLE) {
    const entryPoint = path.join(HOOKS_DIR, hook);
    const outfile = path.join(DIST_DIR, hook);

    if (!fs.existsSync(entryPoint)) {
      console.warn(`Warning: ${hook} not found, skipping`);
      continue;
    }

    console.log(`Bundling ${hook}...`);

    await esbuild.build({
      entryPoints: [entryPoint],
      bundle: true,
      platform: 'node',
      target: 'node18',
      outfile,
      format: 'cjs',
      // Inline WASM as base64 for sql.js
      loader: {
        '.wasm': 'binary'
      },
      external: [],
      minify: true,
      keepNames: true,
      define: {
        'process.env.NODE_ENV': '"production"'
      }
    });

    console.log(`  → ${outfile}`);
  }

  console.log('\nBuild complete.');
}

build().catch(err => {
  console.error('Build failed:', err);
  process.exit(1);
});
