resource "aws_api_gateway_rest_api" "this" {
  name = "whiteborag"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "captures" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "captures"
}

resource "aws_api_gateway_method" "post_captures" {
  rest_api_id      = aws_api_gateway_rest_api.this.id
  resource_id      = aws_api_gateway_resource.captures.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "post_captures" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.captures.id
  http_method             = aws_api_gateway_method.post_captures.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.presign.invoke_arn
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.presign.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/POST/captures"
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  # Redeploy whenever the API surface changes. Hash only configured fields:
  # whole resource objects include provider-computed attributes that settle
  # after the first apply and would force a spurious redeploy.
  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.captures.path_part,
      aws_api_gateway_method.post_captures.http_method,
      aws_api_gateway_method.post_captures.authorization,
      aws_api_gateway_method.post_captures.api_key_required,
      aws_api_gateway_integration.post_captures.type,
      aws_api_gateway_integration.post_captures.integration_http_method,
      aws_api_gateway_integration.post_captures.uri,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = "v1"
}

resource "aws_api_gateway_usage_plan" "devices" {
  name = "whiteborag-devices"

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.v1.stage_name
  }

  throttle_settings {
    rate_limit  = 1
    burst_limit = 5
  }

  quota_settings {
    limit  = 500
    period = "DAY"
  }
}

resource "aws_api_gateway_api_key" "device" {
  for_each = toset(var.devices)
  name     = each.key
}

resource "aws_api_gateway_usage_plan_key" "device" {
  for_each      = aws_api_gateway_api_key.device
  key_id        = each.value.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.devices.id
}

locals {
  # API key ID -> device ID, consumed by the Lambda's DEVICE_KEYS.
  device_keys = { for device, key in aws_api_gateway_api_key.device : key.id => device }
}
