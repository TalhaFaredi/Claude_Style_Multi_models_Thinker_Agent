# README screenshots

These images show the running app's offline demo with fresh browser sessions. Sample models, answers, prices and the PDF card are illustrative. Capture never starts the backend or calls an inference provider.

From `frontend/`, after `npm ci`, use PowerShell:

```powershell
$env:MMA_DEMO='1'
$env:NEXT_BUILD_DIR='.next-readme'
npm run build:webpack
node e2e/screenshots.mjs
```

On macOS/Linux:

```bash
MMA_DEMO=1 NEXT_BUILD_DIR=.next-readme npm run build:webpack
node e2e/screenshots.mjs
```

An installed Chrome or Edge is required. The script uses Edge on Windows and Chrome elsewhere; set `E2E_CHANNEL=chrome` or `msedge` to override. It starts its own server on port 3142, captures five desktop images and closes the browser/server. Images are written here.

Use a new terminal for normal builds afterward so demo build variables are not reused.
