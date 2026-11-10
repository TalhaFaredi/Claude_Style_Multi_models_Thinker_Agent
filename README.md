# Multi-Mode AI Assistant - Frontend

## Repository branches

- [main](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/main): backend source (default branch).
- [backend](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/backend): the same backend release.
- [frontend](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/frontend): Next.js frontend source.

Code keeps its original `backend/` or `frontend/` directory. Clone the backend and frontend branches into separate directories to run both services.

## Run the frontend

Requires Node 20+. Start the backend at http://localhost:8000, then:

```powershell
cd frontend
npm ci
# Create .env.local containing: NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev:webpack
```

Open http://localhost:3000. Without `NEXT_PUBLIC_API_URL`, the interface uses a scripted demo. Provider keys belong only in the backend environment.

## Verify

```powershell
cd frontend
npm test
npm run typecheck
npm run build:webpack
```

Fonts and licenses are bundled locally.

See [frontend/README.md](frontend/README.md) for configuration and source details.
