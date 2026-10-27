# DynamoDB Schema

## UsersTable
- **PK**: `userId`
- Fields: `email`, `currencyPreference`, `createdAt`

## TransactionsTable
- **PK**: `userId`
- **SK**: `transactionDate`
- Additional fields: `transactionId`, `merchant`, `amount`, `category`, `paymentMethod`, `uploadId`, `createdAt`
- GSI: `TransactionIdIndex`
  - **PK**: `transactionId`

## UploadsTable
- **PK**: `uploadId`
- Fields: `userId`, `fileName`, `s3Key`, `status`, `uploadedAt`, `contentType`
- GSI: `UserUploadsIndex`
  - **PK**: `userId`
  - **SK**: `uploadedAt`
