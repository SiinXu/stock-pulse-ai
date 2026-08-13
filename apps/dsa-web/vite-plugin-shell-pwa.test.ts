// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest'
import { collectSyncShellAssetPaths } from './vite-plugin-shell-pwa'

describe('collectSyncShellAssetPaths', () => {
  it('includes the entry graph and CSS, and skips lazy chunks', () => {
    const urls = collectSyncShellAssetPaths({
      'assets/index-abc.js': {
        type: 'chunk',
        isEntry: true,
        imports: [
          'assets/vendor-react-def.js',
          'assets/vendor-router-ghi.js',
        ],
        viteMetadata: { importedCss: ['assets/index-abc.css'] },
      },
      'assets/vendor-react-def.js': {
        type: 'chunk',
        imports: ['assets/vendor-xyz.js'],
      },
      'assets/vendor-router-ghi.js': {
        type: 'chunk',
        imports: ['assets/vendor-icons-jkl.js'],
      },
      'assets/vendor-icons-jkl.js': { type: 'chunk', imports: [] },
      'assets/vendor-xyz.js': { type: 'chunk', imports: [] },
      'assets/HomePage-lazy.js': {
        type: 'chunk',
        imports: ['assets/vendor-charts-lazy.js'],
      },
      'assets/vendor-charts-lazy.js': { type: 'chunk', imports: [] },
    })

    expect(urls.sort()).toEqual([
      '/assets/index-abc.css',
      '/assets/index-abc.js',
      '/assets/vendor-icons-jkl.js',
      '/assets/vendor-react-def.js',
      '/assets/vendor-router-ghi.js',
      '/assets/vendor-xyz.js',
    ])
  })
})
