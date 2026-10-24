# Ingest Lambda: S3 sends each new capture to the ingest queue, and the queue triggers this Lambda.

locals {
  transcript_prefix = "transcripts/"
  nova_model        = "global.amazon.nova-2-lite-v1:0"
  nova_foundation   = "amazon.nova-2-lite-v1:0"
  check_model       = "apac.amazon.nova-pro-v1:0" # the photo check: only Nova Pro spotted a finger over the board
  check_foundation  = "amazon.nova-pro-v1:0"
  embed_model       = "amazon.titan-embed-text-v2:0"
}

data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/whiteborag-ingest"
  retention_in_days = 30
}

resource "aws_iam_role" "ingest" {
  name               = "whiteborag-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid     = "ReadCapturesAndTranscripts"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.captures.arn}/${local.capture_prefix}*",
      "${aws_s3_bucket.captures.arn}/${local.transcript_prefix}*",
    ]
  }

  statement {
    sid       = "WriteTranscripts"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.captures.arn}/${local.transcript_prefix}*"]
  }

  # A photo the check judges unusable is deleted along with any transcripts of it.
  statement {
    sid     = "DeleteUnusableCaptures"
    actions = ["s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.captures.arn}/${local.capture_prefix}*",
      "${aws_s3_bucket.captures.arn}/${local.transcript_prefix}*",
    ]
  }

  # Without ListBucket a missing key reads as AccessDenied, not NoSuchKey. No s3:prefix condition:
  # the check S3 makes during GetObject carries no prefix, so a condition would never match.
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.captures.arn]
  }

  # A global or APAC inference profile can route to the foundation model in another region.
  statement {
    sid     = "InvokeModels"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:ap-south-1:${data.aws_caller_identity.current.account_id}:inference-profile/${local.nova_model}",
      "arn:aws:bedrock:*::foundation-model/${local.nova_foundation}",
      "arn:aws:bedrock:::foundation-model/${local.nova_foundation}",
      "arn:aws:bedrock:ap-south-1:${data.aws_caller_identity.current.account_id}:inference-profile/${local.check_model}",
      "arn:aws:bedrock:*::foundation-model/${local.check_foundation}",
      "arn:aws:bedrock:ap-south-1::foundation-model/${local.embed_model}",
    ]
  }

  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.main.arn]
  }

  statement {
    sid       = "Vectors"
    actions   = ["s3vectors:PutVectors", "s3vectors:DeleteVectors", "s3vectors:GetVectors"]
    resources = [aws_s3vectors_index.captures.index_arn]
  }

  statement {
    sid = "ConsumeQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.ingest.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "ingest"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# Built by backend/ingest/scripts/build.py, not by Terraform: it needs aarch64 wheels.
resource "aws_lambda_function" "ingest" {
  function_name    = "whiteborag-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "ingest.handler.lambda_handler"
  memory_size      = 512
  timeout          = 90
  filename         = "${path.module}/build/ingest.zip"
  source_code_hash = filebase64sha256("${path.module}/build/ingest.zip")

  environment {
    variables = {
      TABLE         = aws_dynamodb_table.main.name
      BUCKET        = aws_s3_bucket.captures.id
      VECTOR_BUCKET = aws_s3vectors_vector_bucket.main.vector_bucket_name
      VECTOR_INDEX  = aws_s3vectors_index.captures.index_name
      NOVA_MODEL    = local.nova_model
      CHECK_MODEL   = local.check_model
      EMBED_MODEL   = local.embed_model
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest, aws_iam_role_policy.ingest]
}

# One message per invocation, so a failure retries only that capture. Two at once at most,
# to stay well inside Bedrock's quotas. The handler reports failures per message.
resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn        = aws_sqs_queue.ingest.arn
  function_name           = aws_lambda_function.ingest.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 2
  }
}

# S3 may send to the queue, but only for this bucket in this account.
data "aws_iam_policy_document" "ingest_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.captures.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "ingest" {
  queue_url = aws_sqs_queue.ingest.id
  policy    = data.aws_iam_policy_document.ingest_queue.json
}

# S3 checks it can send to the queue when the notification is created, so the policy must exist first.
resource "aws_s3_bucket_notification" "captures" {
  bucket = aws_s3_bucket.captures.id

  queue {
    queue_arn     = aws_sqs_queue.ingest.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = local.capture_prefix
    filter_suffix = ".jpg"
  }

  depends_on = [aws_sqs_queue_policy.ingest]
}
