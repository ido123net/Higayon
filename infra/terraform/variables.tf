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

variable "hostname" {
  type = string
}

variable "owner_email" {
  type = string
}

variable "allowed_emails" {
  type = list(string)
}

variable "tls_secret_name" {
  type    = string
  default = "higayon-tls"
}

variable "tls_issuer_name" {
  type        = string
  description = "Existing cert-manager ClusterIssuer used for the Ingress TLS secret."
  default     = "letsencrypt-production"
  validation {
    condition     = contains(["letsencrypt-staging", "letsencrypt-production"], var.tls_issuer_name)
    error_message = "Choose the configured letsencrypt-staging or letsencrypt-production ClusterIssuer."
  }
}

variable "ingress_class" {
  type    = string
  default = "nginx"
}

variable "ingress_enabled" {
  type    = bool
  default = true
}
