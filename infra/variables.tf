variable "devices" {
  description = "Device IDs; each gets its own API key."
  type        = list(string)
  default     = ["wb-cam-01"]

  validation {
    condition     = alltrue([for d in var.devices : can(regex("^[a-z0-9-]{1,32}$", d))])
    error_message = "Each device ID must match ^[a-z0-9-]{1,32}$."
  }
}

variable "alert_email" {
  description = "Email address that receives the ingest DLQ alarm. Confirm the subscription email AWS sends."
  type        = string
}
