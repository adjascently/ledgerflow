#!/usr/bin/env python3
import aws_cdk as cdk

from workflow_stack import WorkflowEventsStack


app = cdk.App()
WorkflowEventsStack(app, "WorkflowEventsStack")
app.synth()
