import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/geist/index.css'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme/ThemeProvider'

if (import.meta.env.DEV) {
  // Loupe dev annotator is an optional local tool; skip silently if not installed.
  try {
    // Resolved via vite alias when present, or the catch below when absent.
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore optional dependency, may be unresolved in a clean checkout
    const { installAnnotator } = await import("@loupe/dev-annotator")
    installAnnotator({ appName: "DSA Web" })
  } catch {
    // no-op: optional dependency not present in this environment
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
)
