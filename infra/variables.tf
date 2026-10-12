variable "devices" {
  description = "Device IDs; each gets its own API key."
  type        = list(string)
  default     = ["wb-cam-01"]

  validation {
    condition     = alltrue([for d in var.devices : can(regex("^[a-z0-9-]{1,32}$", d))])
    error_message = "Each device ID must match ^[a-z0-9-]{1,32}$."
  }
}
