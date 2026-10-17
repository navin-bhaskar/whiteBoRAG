# Ingest queue: S3 writes capture events here (queue policy and notification in Task 15's ingest.tf),
# the ingest Lambda consumes them, and a message that fails 3 times moves to the DLQ.

resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "whiteborag-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days, the SQS maximum: time to fix the cause and redrive.
}

resource "aws_sqs_queue" "ingest" {
  name = "whiteborag-ingest"
  # 6 x the Lambda's 90 s timeout, so a message in flight isn't handed to a second Lambda.
  visibility_timeout_seconds = 540
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}

# Alerting: anything in the DLQ emails the user.

resource "aws_sns_topic" "alerts" {
  name = "whiteborag-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "whiteborag-ingest-dlq-not-empty"
  alarm_description   = "A capture failed ingestion 3 times and is in the DLQ. Fix the cause, then run redrive_dlq.py."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.ingest_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
