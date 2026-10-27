# SNS Setup Notes

## Purpose

Amazon SNS is used to send notification emails after the workflow finishes processing an uploaded statement.

In this module, SNS is responsible for:
- sending success notifications
- sending threshold-exceeded alerts
- sending failure notifications

## Resource Name

Topic name used:
`finance-tracker-alert-topic`

## Setup Steps

1. Open **Amazon SNS**
2. Create a **Standard** topic
3. Set the topic name to:
   `finance-tracker-alert-topic`
4. Create an email subscription
5. Confirm the subscription from the email inbox

## Usage in This Module

The Lambda function publishes alerts to this SNS topic.
The Step Functions workflow can also publish notifications directly.

## Important Notes

- Email subscriptions must be confirmed before notifications will be delivered
- For testing, one email subscriber is enough
- For a shared team setup, additional team member emails can be subscribed to the same topic