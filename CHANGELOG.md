### v 2.5.1.3 - Persisted cookie settings and worker sync
* Persist cookie-related preferences immediately when changed in the Preferences dialog.
* Record a timestamped “last imported” cookie marker when cookies are exported from a browser.
* Ensure all worker modules that may refresh cookies (download, title-fetch, metadata) update AppSettings and persist the new cookie info as a best-effort operation.

### v 2.5.1.2 - Dynamic cookies, safer exports, and automatic refresh
* Added a secure cookie management flow that imports browser cookies, prunes them to avoid oversized headers, and optionally refreshes them automatically before metadata fetches and downloads.
* Integrated cookie refresh into title/metadata fetch workers and the download worker so authenticated downloads are more reliable without repeated manual exports.
* Fixed HTTP 413 failures caused by huge exported cookie dumps and improved UX around importing, persisting, and clearing cookies.

### v 2.5.1.1 - Console Log Limit and Performance Improvements
* Added a hard limit to the in-memory console log so the app keeps at most 200 log lines.
* Reduced UI work when appending logs by appending the newest entry directly when console filter is "All".
* Trimmed oldest entries automatically to prevent unbounded memory growth and excessive QTextEdit re-renders.
