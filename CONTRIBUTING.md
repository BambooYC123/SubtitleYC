# Contributing to SubtitleYC

Thank you for helping improve SubtitleYC.

## Getting Started

1. Fork the repository and create a branch for your change.
2. Create and activate a Python 3.10 or newer virtual environment.
3. Install the project in editable mode with development dependencies:

   ```powershell
   python -m pip install -e ".[dev]"
   ```

4. Keep changes focused and follow the existing project structure.
5. Add or update tests when behavior changes.

## Testing

Run the automated checks before opening a pull request:

```powershell
python -m unittest discover -s tests
python -m compileall subtitleyc tests
```

If Node.js is installed, also check the JavaScript entry points:

```powershell
node --check static\app.js
node --check static\editor.js
```

## Pull Requests

Describe the problem, the approach taken, and how the change was verified.
Do not include private media, credentials, cookies, access tokens, generated
workspaces, build output, or third-party binaries.

By contributing, you agree that your contribution is licensed under the MIT
License in `LICENSE`.

## Security Reports

Do not open a public issue for a suspected vulnerability. Follow
`SECURITY.md` instead.
