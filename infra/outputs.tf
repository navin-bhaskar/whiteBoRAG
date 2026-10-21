output "api_base_url" {
  description = "POST {api_base_url}/captures"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "api_keys" {
  description = "Device ID -> API key value (put into the device's secrets.h)."
  value       = { for device, key in aws_api_gateway_api_key.device : device => key.value }
  sensitive   = true
}

output "query_url" {
  description = "POST questions here from the local page."
  value       = "${aws_api_gateway_stage.v1.invoke_url}/query"
}

output "query_api_key" {
  description = "The query-local API key; read with: terraform output -raw query_api_key"
  value       = aws_api_gateway_api_key.query.value
  sensitive   = true
}

output "ingest_queue_url" {
  description = "Queue S3 sends capture events to; the ingest Lambda consumes it."
  value       = aws_sqs_queue.ingest.id
}

output "ingest_dlq_url" {
  description = "Captures that failed ingestion 3 times; redrive with redrive_dlq.py."
  value       = aws_sqs_queue.ingest_dlq.id
}
