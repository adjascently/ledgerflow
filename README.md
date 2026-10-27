# Smart Personal Finance Tracker

Unified project workspace for the team build:
- `frontend/` contains the React web app and Cognito client integration.
- `backend/` contains the REST API, Lambda handlers, data models, and CDK stack.
- `workflow-events-notifications/` contains the event pipeline assets for statement processing.
- `analytics-ml-monitoring/` contains Person 4 analytics, SageMaker, monitoring, and reporting documentation/assets.
- `shared/` contains common schemas, constants, and sample events.
- `docs/` stores architecture references, screenshots, and setup notes.

## Primary deployment entry points
- Backend and analytics infrastructure: `backend/infra`
- Frontend app: `frontend`
- Workflow assets and notes: `workflow-events-notifications`
- Analytics/ML setup notes: `analytics-ml-monitoring`
- Public frontend hosting: AWS Amplify Hosting using the root [amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/amplify.yml:1) or [frontend/amplify.yml](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/frontend/amplify.yml:1)

## Quick start
```bash
cd backend/infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g aws-cdk
cdk bootstrap
cdk deploy
```

After backend deployment:
1. Configure the frontend environment in `frontend/.env`.
2. Run the frontend from `frontend/`.
3. Follow the workflow module README for the event pipeline and the analytics module README for monitoring plus optional future reporting extensions.

## Public URL with Amplify
For a public URL, host the React frontend on AWS Amplify Hosting and keep the backend, workflow, Cognito, and analytics stacks exactly as deployed today.

Amplify deployment essentials:
1. Use region `us-west-2`.
2. Set hosted environment variables for:
   - `VITE_API_BASE_URL`
   - `VITE_COGNITO_USER_POOL_ID`
   - `VITE_COGNITO_CLIENT_ID`
   - `VITE_AWS_REGION`
3. Add the SPA rewrite rule:
   - source: `/<*>`
   - target: `/index.html`
   - type: `200 (Rewrite)`

This is the preferred public-hosting path for the project. EC2 is unnecessary unless you are explicitly required to use it.
---
