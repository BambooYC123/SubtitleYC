# SubtitleYC Security Policy

## Supported Versions

During public beta, security fixes are provided for the latest published beta
only. Older builds may remain usable but are not promised security updates.

## Reporting a Vulnerability

Do not publish a suspected vulnerability as a public issue. Use GitHub Private
Vulnerability Reporting on the official SubtitleYC releases repository. If
that option is unavailable, use the private support contact listed on the
official release page.

Include the SubtitleYC version and edition, Windows version, steps to reproduce,
and the smallest non-sensitive log excerpt needed to explain the issue. Do not
send credentials, cookies, access tokens, private URLs, or private media.

Reports will be assessed on a best-effort basis during beta. Please allow a
reasonable period for investigation and a fixed release before publicly
disclosing a confirmed vulnerability.

## Release Verification

Download SubtitleYC only from its official release page. Every release asset
is published with a SHA-256 checksum. Public beta installers may be unsigned;
the release notes must clearly identify signing status. A paid production
release should be Authenticode-signed and timestamped.

## Security Boundaries

SubtitleYC processes local media and can contact user-selected video websites
through yt-dlp. Its desktop backend binds to `127.0.0.1`, uses an app-session
token, blocks private-address URL targets, redacts common sensitive log data,
and applies restricted Qt WebEngine navigation and permission policies.

These controls reduce risk but do not make untrusted media, websites, or files
safe. Keep Windows, GPU drivers, SubtitleYC, yt-dlp, and antivirus protection
up to date, and do not use the app to bypass access controls.

