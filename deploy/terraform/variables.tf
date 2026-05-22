variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "astra"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "CPU units for Fargate task"
  type        = number
  default     = 512
}

variable "memory" {
  description = "Memory (MB) for Fargate task"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Desired number of Fargate tasks"
  type        = number
  default     = 1
}

variable "astra_db_path" {
  description = "Path to ASTRA SQLite DB inside container"
  type        = string
  default     = "/data/astra.db"
}

variable "astra_build_dir" {
  description = "Build output directory"
  type        = string
  default     = "/data/builds"
}

variable "astra_export_dir" {
  description = "Export output directory"
  type        = string
  default     = "/data/exports"
}
