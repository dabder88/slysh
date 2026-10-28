# Slysh! v1.0.6

## Summary

- Fix invalid import map JSON that broke the UI with a red error banner.
- YouTube reachability check uses GET generate_204 and the correct proxy opener.
- Add youtube_proxy_active to status; hide misleading “enable proxy” toast when YouTube proxy is on.
- Try transcript-api fallback when YouTube proxy is active even if preflight fails.

**Website:** https://slyshai.pro/

## Assets

- `Slysh-Setup-1.0.6-ru.exe`
- `Slysh-Setup-1.0.6-en.exe`
- `Slysh-Setup-ru.exe` (same bytes as versioned RU; README download)
- `Slysh-Setup-en.exe` (same bytes as versioned EN; README download)

## SHA-256 (required for in-app update)

```
sha256: 9782c5675f0da9673266b0f8620dfb177efdd8c4b00f89a9297b43a0744b9a41  Slysh-Setup-1.0.6-ru.exe
sha256: bc3119a594f5b99a16166ba63f834f7554f6ee24720e345239041c34abac6799  Slysh-Setup-1.0.6-en.exe
```

Build: 2026-10-28 (payload-build `97a178cf19d355a9`).
