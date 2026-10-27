# Amplify Hosting

Use AWS Amplify Hosting to expose the frontend with a public URL.

## Recommended deployment shape
- Host only the React/Vite app.
- Keep backend APIs on API Gateway/Lambda.
- Keep workflow and analytics infrastructure unchanged.
- Keep Cognito unchanged.

## Region
- Use `us-west-2` so the frontend aligns with the deployed backend and Cognito resources.

## Build config
If you connect the whole repository to Amplify, use the root [amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/amplify.yml:1).

If you upload or point Amplify directly at the `frontend/` directory, use [frontend/amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/frontend/amplify.yml:1).

## Required Amplify environment variables
- `VITE_API_BASE_URL`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `VITE_AWS_REGION`

Use the same values that work in local frontend development.

## Required rewrite rule
Because the app uses `BrowserRouter`, add this Amplify rewrite:

- source: `/<*>`
- target: `/index.html`
- type: `200 (Rewrite)`

Without this rule, direct navigation or page refreshes on routes like `/dashboard` and `/transactions` will fail.

## Validation checklist
1. Open the Amplify public URL.
2. Sign in with Cognito.
3. Visit `/dashboard`, `/upload`, `/transactions`, and `/alerts` directly.
4. Refresh the page on one of those routes.
5. Upload a statement and verify the API calls succeed.
