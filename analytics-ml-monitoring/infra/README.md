# Analytics Infrastructure Notes

This folder contains deployment notes for the analytics and ML slice.

The CDK implementation itself lives in `../../backend/infra` so analytics services can share the API, DynamoDB tables, and Lambda environment configuration already defined in the backend stack.
