import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// The Loupe dev annotator is an optional local tool (optionalDependencies).
// Only wire it into dev optimizeDeps when it actually resolves, so a clean
// checkout without the sibling clone still runs dev/build.
const isLoupeAvailable = (() => {
  try {
    createRequire(import.meta.url).resolve('@loupe/dev-annotator')
    return true
  } catch {
    return false
  }
})()

const packageJson = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf-8'),
) as { version?: string }
const buildTime = new Date().toISOString()

const vendorChunkByPackage: Record<string, string> = {
  react: 'vendor-react',
  'react-dom': 'vendor-react',
  scheduler: 'vendor-react',
  'react-router': 'vendor-router',
  'react-router-dom': 'vendor-router',
  motion: 'vendor-motion',
  'framer-motion': 'vendor-motion',
  'motion-dom': 'vendor-motion',
  'motion-utils': 'vendor-motion',
  'lucide-react': 'vendor-icons',
  recharts: 'vendor-charts',
  'victory-vendor': 'vendor-charts',
  '@reduxjs/toolkit': 'vendor-charts',
  'decimal.js-light': 'vendor-charts',
  'es-toolkit': 'vendor-charts',
  eventemitter3: 'vendor-charts',
  immer: 'vendor-charts',
  'react-redux': 'vendor-charts',
  reselect: 'vendor-charts',
  'tiny-invariant': 'vendor-charts',
  'use-sync-external-store': 'vendor-charts',
  // Markdown renderer dependencies that are not covered by prefix rules below.
  'react-markdown': 'vendor-markdown',
  unified: 'vendor-markdown',
  vfile: 'vendor-markdown',
  'remove-markdown': 'vendor-markdown',
  bail: 'vendor-markdown',
  'comma-separated-tokens': 'vendor-markdown',
  'decode-named-character-reference': 'vendor-markdown',
  devlop: 'vendor-markdown',
  'html-url-attributes': 'vendor-markdown',
  'property-information': 'vendor-markdown',
  'space-separated-tokens': 'vendor-markdown',
  'trim-lines': 'vendor-markdown',
  'vfile-message': 'vendor-markdown',
}

const vendorChunkByPackagePrefix: Array<[string, string]> = [
  ['d3-', 'vendor-charts'],
  ['remark-', 'vendor-markdown'],
  ['micromark', 'vendor-markdown'],
  ['mdast-util-', 'vendor-markdown'],
  ['hast-util-', 'vendor-markdown'],
  ['unist-util-', 'vendor-markdown'],
]

const getVendorPackageName = (id: string): string | undefined => {
  const normalizedId = id.replace(/\\/g, '/')
  const marker = '/node_modules/'
  const markerIndex = normalizedId.lastIndexOf(marker)
  if (markerIndex === -1) {
    return undefined
  }

  const packagePath = normalizedId.slice(markerIndex + marker.length)
  const [firstSegment, secondSegment] = packagePath.split('/')
  if (!firstSegment) {
    return undefined
  }

  if (firstSegment.startsWith('@')) {
    return secondSegment ? `${firstSegment}/${secondSegment}` : undefined
  }

  return firstSegment
}

const getVendorChunkName = (id: string): string | undefined => {
  const packageName = getVendorPackageName(id)
  if (!packageName) {
    return undefined
  }

  return (
    vendorChunkByPackage[packageName]
    ?? vendorChunkByPackagePrefix.find(([prefix]) => packageName.startsWith(prefix))?.[1]
    ?? 'vendor'
  )
}

// https://vite.dev/config/
export default defineConfig({
  define: {
    __APP_PACKAGE_VERSION__: JSON.stringify(packageJson.version ?? '0.0.0'),
    __APP_BUILD_TIME__: JSON.stringify(buildTime),
  },
  // Ensure the symlinked @loupe/dev-annotator resolves the app's single React copy
  // instead of a second one from the linked package's own node_modules.
  resolve: {
    dedupe: ['react', 'react-dom'],
    // When the optional Loupe package is absent, alias it to a local no-op stub
    // so dev/build resolve cleanly instead of failing on a missing module.
    alias: isLoupeAvailable
      ? {}
      : { '@loupe/dev-annotator': path.resolve(__dirname, 'src/dev/loupeStub.ts') },
  },
  optimizeDeps: {
    include: isLoupeAvailable ? ['@loupe/dev-annotator'] : [],
  },
  plugins: [
    tailwindcss(),
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',  // Allow public access
    port: 5173,       // Default port
    proxy: {
      '/api': {
        target: process.env.DSA_WEB_DEV_API_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Package output to the static folder in the project root directory
    outDir: path.resolve(__dirname, '../../static'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: getVendorChunkName,
      },
    },
  },
})
