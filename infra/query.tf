# Query Lambda: answers questions about stored boards for the local page. Read-only on all data.

resource "aws_cloudwatch_log_group" "query" {
  name              = "/aws/lambda/whiteborag-query"
  retention_in_days = 30
}

resource "aws_iam_role" "query" {
  name               = "whiteborag-query"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "query" {
  # Photos for signing image URLs (a signed URL works only if the signer may read the object),
  # transcripts as evidence.
  statement {
    sid     = "ReadCapturesAndTranscripts"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.captures.arn}/${local.capture_prefix}*",
      "${aws_s3_bucket.captures.arn}/${local.transcript_prefix}*",
    ]
  }

  # Without ListBucket a missing key reads as AccessDenied, not NoSuchKey.
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.captures.arn]
  }

  statement {
    sid     = "InvokeModels"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:ap-south-1:${data.aws_caller_identity.current.account_id}:inference-profile/${local.nova_model}",
      "arn:aws:bedrock:*::foundation-model/${local.nova_foundation}",
      "arn:aws:bedrock:::foundation-model/${local.nova_foundation}",
      "arn:aws:bedrock:ap-south-1::foundation-model/${local.embed_model}",
    ]
  }

  statement {
    sid       = "ReadTable"
    actions   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
    resources = [aws_dynamodb_table.main.arn]
  }

  # QueryVectors also needs GetVectors when it returns metadata or filters on it.
  statement {
    sid       = "SearchVectors"
    actions   = ["s3vectors:QueryVectors", "s3vectors:GetVectors"]
    resources = [aws_s3vectors_index.captures.index_arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.query.arn}:*"]
  }
}

resource "aws_iam_role_policy" "query" {
  name   = "query"
  role   = aws_iam_role.query.id
  policy = data.aws_iam_policy_document.query.json
}

# Built by backend/query/scripts/build.py; it bundles the ingest package the handler imports.
# Timeout 28 s: API Gateway gives up at 29 s, so the Lambda's own 500 (with CORS) reaches the page first.
resource "aws_lambda_function" "query" {
  function_name    = "whiteborag-query"
  role             = aws_iam_role.query.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "query.handler.lambda_handler"
  memory_size      = 512
  timeout          = 28
  filename         = "${path.module}/build/query.zip"
  source_code_hash = filebase64sha256("${path.module}/build/query.zip")

  environment {
    variables = {
      TABLE          = aws_dynamodb_table.main.name
      BUCKET         = aws_s3_bucket.captures.id
      VECTOR_BUCKET  = aws_s3vectors_vector_bucket.main.vector_bucket_name
      VECTOR_INDEX   = aws_s3vectors_index.captures.index_name
      NOVA_MODEL     = local.nova_model
      EMBED_MODEL    = local.embed_model
      QUERY_KEY_ID   = aws_api_gateway_api_key.query.id
      ALLOWED_ORIGIN = var.query_origin
    }
  }

  depends_on = [aws_cloudwatch_log_group.query, aws_iam_role_policy.query]
}

resource "aws_lambda_permission" "query" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/POST/query"
}

# A usage plan covers the whole stage, so this key also passes API Gateway's check on /captures
# (and device keys on /query). Each Lambda enforces the split: presign accepts only device keys,
# query only QUERY_KEY_ID.
resource "aws_api_gateway_api_key" "query" {
  name = "query-local"
}

resource "aws_api_gateway_usage_plan" "query" {
  name = "whiteborag-query"

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.v1.stage_name
  }

  throttle_settings {
    rate_limit  = 2
    burst_limit = 5
  }

  quota_settings {
    limit  = 1000
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "query" {
  key_id        = aws_api_gateway_api_key.query.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.query.id
}
