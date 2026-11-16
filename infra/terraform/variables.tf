variable "kubeconfig" {
  type    = string
  default = "~/.kube/config"
}

variable "context" {
  type    = string
  default = null
}

variable "namespace" {
  type    = string
  default = "higayon"
}

variable "image" {
  type = string
}

variable "hostname" {
  type = string
}

variable "owner_email" {
  type = string
}

variable "allowed_emails" {
  type = list(string)
}

variable "runtime_secret_name" {
  type    = string
  default = "higayon-runtime"
}

variable "tls_secret_name" {
  type    = string
  default = "higayon-tls"
}

variable "ingress_class" {
  type    = string
  default = "nginx"
}

variable "ingress_enabled" {
  type    = bool
  default = true
}

variable "replicas" {
  type    = number
  default = 1
}

variable "release" {
  type    = string
  default = "v1"
}

variable "resource_requests" {
  type    = map(string)
  default = { cpu = "100m", memory = "128Mi" }
}

variable "resource_limits" {
  type    = map(string)
  default = { cpu = "1", memory = "512Mi" }
}
