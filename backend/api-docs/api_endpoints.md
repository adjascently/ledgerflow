# API Endpoints

## 1. Create user
**POST** `/user`

Request body:
```json
{
  "userId": "user-123",
  "email": "user@example.com",
  "currencyPreference": "USD"
}
```

## 2. Generate statement upload URL
**POST** `/statement/upload`

Request body:
```json
{
  "userId": "user-123",
  "fileName": "march_statement.pdf",
  "contentType": "application/pdf"
}
```

Response:
```json
{
  "uploadId": "...",
  "s3Key": "statements/user-123/<uploadId>.pdf",
  "uploadUrl": "...",
  "expiresIn": 900
}
```

## 3. Save transactions
**POST** `/transactions`

Request body:
```json
{
  "userId": "user-123",
  "transactions": [
    {
      "transactionId": "txn-001",
      "date": "2026-04-01",
      "merchant": "Trader Joe's",
      "amount": 48.12,
      "category": "Groceries",
      "paymentMethod": "Credit Card",
      "uploadId": "upload-123"
    }
  ]
}
```

## 4. Get transactions
**GET** `/transactions/{userId}?startDate=2026-04-01&endDate=2026-04-30`

## 5. Monthly summary
**GET** `/summary/monthly/{userId}?month=2026-04`

## 6. Category spending
**GET** `/analytics/category/{userId}?month=2026-04`

## 7. Analytics overview
**GET** `/analytics/overview/{userId}?month=2026-04&months=6`

Response:
```json
{
  "userId": "user-123",
  "focusMonth": "2026-04",
  "monthsAnalyzed": 6,
  "totals": {
    "totalSpent": 1432.56,
    "transactionCount": 27,
    "averageTransaction": 53.06,
    "topCategory": "Groceries",
    "topMerchant": "Trader Joe's",
    "previousMonthTotalSpent": 1189.12,
    "changeFromPreviousMonthPct": 20.5,
    "predictedNextMonthSpend": 1368.43
  },
  "monthlyTrend": [
    { "month": "2026-01", "totalSpent": 912.33, "transactionCount": 18, "averageTransaction": 50.69, "topCategory": "Dining" }
  ],
  "dailySpend": [
    { "date": "2026-04-02", "amount": 84.15 }
  ],
  "categoryBreakdown": [
    { "category": "Groceries", "amount": 410.55, "transactionCount": 8, "averageAmount": 51.32, "share": 28.7 }
  ],
  "topMerchants": [
    { "merchant": "Trader Joe's", "amount": 210.44, "transactionCount": 4 }
  ],
  "anomalyCandidates": [
    {
      "transactionId": "txn-901",
      "date": "2026-04-14",
      "merchant": "Airline",
      "category": "Travel",
      "amount": 312.11,
      "reason": "2.3x higher than your usual travel spend"
    }
  ],
  "alerts": [
    {
      "type": "spending-increase",
      "severity": "warning",
      "title": "Monthly spending is trending up",
      "message": "You are up 20.5% versus last month."
    }
  ]
}
```

## 8. ML predictions
**GET** `/ml/predictions/{userId}?month=2026-04&months=6`

Response:
```json
{
  "userId": "user-123",
  "focusMonth": "2026-04",
  "prediction": {
    "source": "heuristic",
    "modelName": "baseline-ml-fallback-v1",
    "forecastAmount": 1380.42,
    "forecastConfidence": "medium",
    "predictedTopCategories": [
      {
        "category": "Groceries",
        "confidence": 0.74,
        "reason": "Groceries has been one of the strongest spending categories in the recent history."
      }
    ],
    "anomalyRisk": {
      "level": "medium",
      "score": 0.48,
      "reason": "Derived from month-over-month changes and unusually large transactions."
    }
  },
  "recommendedActions": [
    "Refresh the reporting dashboard after new statement uploads so the web dashboard and reporting tables stay current."
  ]
}
```
