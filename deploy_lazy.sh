#!/bin/bash
rm -rf slack_bolt && mkdir slack_bolt && cp -pr /opt/homebrew/lib/python3.10/site-packages/slack_bolt/* slack_bolt/
pip install python-lambda -U
lambda deploy \
  --config-file lazy_aws_lambda_config.yaml \
  --requirements requirements.txt