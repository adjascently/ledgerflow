# Frontend

React + Vite frontend for authentication, uploads, transactions, and alerts.

## Main areas
- Login and signup via Cognito config in `src/amplifyConfig.ts`
- Protected app shell and routes
- Upload flow for bank statements
- Transactions and summary views

## Run locally
```bash
npm install
npm run dev
```

## Required environment values
- `VITE_API_BASE_URL`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `VITE_AWS_REGION`

## Public hosting with AWS Amplify
This frontend is intended to be hosted as a static SPA on AWS Amplify Hosting.

Recommended setup:
1. Open Amplify in `us-west-2`.
2. Create a new app.
3. If you connect the whole repository, use the root [amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/amplify.yml:1).
4. If you deploy only the `frontend/` folder, use the local [frontend/amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/frontend/amplify.yml:1).
5. Set these environment variables in Amplify instead of using `.env`:
   - `VITE_API_BASE_URL`
   - `VITE_COGNITO_USER_POOL_ID`
   - `VITE_COGNITO_CLIENT_ID`
   - `VITE_AWS_REGION`
6. Add an Amplify rewrite rule for the SPA:
   - source: `/<*>`
   - target: `/index.html`
   - type: `200 (Rewrite)`

The rewrite rule is required because the app uses `BrowserRouter`, so direct visits to `/dashboard`, `/transactions`, `/upload`, and `/alerts` must fall back to `index.html`.
