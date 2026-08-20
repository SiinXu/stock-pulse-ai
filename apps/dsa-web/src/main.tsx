import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/geist/index.css'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme/ThemeProvider'
import { ThemeAppearanceProvider } from './components/theme/ThemeAppearanceProvider'
import { PriceDirectionSync } from './components/theme/PriceDirectionSync'
import { InitialUiLanguageGate } from './i18n/InitialUiLanguageGate'
import { beginInitialUiLanguage } from './i18n/prepareUiLanguage'
import { QueryProvider } from './query/QueryProvider'
import { applyUiLanguageToDocument, getRuntimeInitialLanguage } from './utils/uiLanguage'
import { installApiMockIfEnabled } from './dev/apiMock/apiMockSwitch'
import { registerServiceWorker } from './pwa/registerServiceWorker'

const requestedUiLanguage = getRuntimeInitialLanguage()
const { shell, catalog } = beginInitialUiLanguage(requestedUiLanguage)
applyUiLanguageToDocument(
  shell.status === 'app-ready' ? shell.language : shell.requested,
)

if (import.meta.env.DEV) {
  // Temporary dev API mock switch; no-op unless enabled via ?mock / VITE_MOCK_API.
  await installApiMockIfEnabled()

  // Loupe dev annotator is an optional local tool; skip silently if not installed.
  try {
    // Resolved via vite alias when present, or the catch below when absent.
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore optional dependency, may be unresolved in a clean checkout
    const { installAnnotator } = await import("@loupe/dev-annotator")
    installAnnotator({ appName: "StockPulse Web" })
  } catch {
    // no-op: optional dependency not present in this environment
  }
}

// Production shell PWA only: caches app shell + static assets, never API/market data.
if (import.meta.env.PROD) {
  void registerServiceWorker({
    enabled: true,
    onError: (error) => {
      console.warn('[pwa] service worker registration failed', error)
    },
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryProvider>
      <ThemeProvider>
        <ThemeAppearanceProvider>
          <PriceDirectionSync />
          <InitialUiLanguageGate
            shell={shell}
            catalog={catalog}
            onLanguage={applyUiLanguageToDocument}
          >
            {(language) => <App initialUiLanguage={language} />}
          </InitialUiLanguageGate>
        </ThemeAppearanceProvider>
      </ThemeProvider>
    </QueryProvider>
  </StrictMode>,
)
