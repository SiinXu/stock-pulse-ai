// No-op stand-in for the optional @loupe/dev-annotator package.
// Vite aliases the package to this file when the sibling clone is not installed,
// so a clean checkout can still run `npm run dev` / `npm run build`.
export function installAnnotator(): void {
  // intentionally empty: the dev annotator is unavailable in this environment
}
