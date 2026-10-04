Offline installer assets (not committed as .exe).

Before ISCC, run from repo root:
  powershell -File scripts\fetch-installer-redist.ps1

Downloads:
  MicrosoftEdgeWebview2Setup.exe — Evergreen Bootstrapper (online install on client).
  MicrosoftEdgeWebView2RuntimeInstallerX64.exe — optional offline standalone (see webview2-standalone.url.example).

When standalone is present, Slysh.iss installs WebView2 without network.
