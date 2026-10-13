locals {
  presign_src = "${path.module}/../backend/presign"
}

# Only the two runtime modules go in the zip: no tests, venv or caches.
data "archive_file" "presign" {
  type        = "zip"
  output_path = "${path.module}/build/presign.zip"

  source {
    filename = "handler.py"
    content  = file("${local.presign_src}/handler.py")
  }

  source {
    filename = "ulid.py"
    content  = file("${local.presign_src}/ulid.py")
  }
}

resource "aws_cloudwatch_log_group" "presign" {
  name              = "/aws/lambda/whiteborag-presign"
  retention_in_days = 30
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "presign" {
  name               = "whiteborag-presign"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "presign" {
  statement {
    sid       = "PutCaptures"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.captures.arn}/${local.capture_prefix}*"]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.presign.arn}:*"]
  }
}

resource "aws_iam_role_policy" "presign" {
  name   = "presign"
  role   = aws_iam_role.presign.id
  policy = data.aws_iam_policy_document.presign.json
}

resource "aws_lambda_function" "presign" {
  function_name    = "whiteborag-presign"
  role             = aws_iam_role.presign.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 128
  timeout          = 5
  filename         = data.archive_file.presign.output_path
  source_code_hash = data.archive_file.presign.output_base64sha256

  environment {
    variables = {
      BUCKET      = aws_s3_bucket.captures.id
      PREFIX      = local.capture_prefix
      URL_TTL     = "300"
      DEVICE_KEYS = jsonencode(local.device_keys)
    }
  }

  depends_on = [aws_cloudwatch_log_group.presign, aws_iam_role_policy.presign]
}
