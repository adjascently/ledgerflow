# SQS Setup Notes

## Purpose

Amazon SQS is used to decouple the workflow from the processing logic.

In this module, SQS acts as an asynchronous buffer between:
- Step Functions
- Lambda processing

This improves reliability and makes the system more scalable.

## Resource Name

Queue name used:
`finance-tracker-statement-queue`

## Setup Steps

1. Open **Amazon SQS**
2. Create a **Standard** queue
3. Set the queue name to:
   `finance-tracker-statement-queue`
4. Keep the default configuration unless custom tuning is required

## Usage in This Module

The Step Functions workflow sends a message to the SQS queue before invoking the processing Lambda.

This demonstrates:
- asynchronous job handling
- decoupled architecture
- scalable event processing

## Important Notes

- A standard queue is sufficient for this project
- Default settings work well for testing and demo purposes
- The queue is used as part of the workflow pipeline, not as a direct user-facing component