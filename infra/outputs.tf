output "api_base_url" {
  description = "POST {api_base_url}/captures"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "api_keys" {
  description = "Device ID -> API key value (put into the device's secrets.h)."
  value       = { for device, key in aws_api_gateway_api_key.device : device => key.value }
  sensitive   = true
}
