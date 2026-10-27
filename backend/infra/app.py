#!/usr/bin/env python3
import aws_cdk as cdk
from backend_stack import FinanceBackendStack

app = cdk.App()
FinanceBackendStack(app, "FinanceBackendStack")
app.synth()
