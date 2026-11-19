terraform {
  required_version = ">= 1.7"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
  }
}
provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig)
  config_context = var.context
}
resource "kubernetes_namespace_v1" "app" {
  metadata { name = var.namespace }
}
resource "kubernetes_config_map_v1" "app" {
  metadata {
    name      = "higayon"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  data = {
    DEBUG                = "false"
    TRUST_PROXY          = "true"
    ALLOWED_HOSTS        = var.hostname
    CSRF_TRUSTED_ORIGINS = "https://${var.hostname}"
    OWNER_EMAIL          = var.owner_email
    ALLOWED_EMAILS       = join(",", var.allowed_emails)
  }
}
locals {
  labels = { app = "higayon" }
}
# Release ownership moves to Kubernetes. Leave the live objects in place.
removed {
  from = kubernetes_job_v1.migrate
  lifecycle { destroy = false }
}

removed {
  from = kubernetes_deployment_v1.app
  lifecycle { destroy = false }
}

resource "kubernetes_service_v1" "app" {
  metadata {
    name      = "higayon"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  spec {
    selector = local.labels
    port {
      port        = 80
      target_port = 8000
    }
  }
}
resource "kubernetes_ingress_v1" "app" {
  count = var.ingress_enabled ? 1 : 0
  metadata {
    name      = "higayon"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    annotations = {
      "cert-manager.io/cluster-issuer" = var.tls_issuer_name
    }
  }
  spec {
    ingress_class_name = var.ingress_class
    tls {
      hosts       = [var.hostname]
      secret_name = var.tls_secret_name
    }
    rule {
      host = var.hostname
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service_v1.app.metadata[0].name
              port { number = 80 }
            }
          }
        }
      }
    }
  }
}

# Headless service gives Prometheus one scrape target per running app pod.
resource "kubernetes_service_v1" "metrics" {
  metadata {
    name      = "higayon-metrics"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  spec {
    cluster_ip = "None"
    selector   = local.labels
    port {
      name        = "metrics"
      port        = 9091
      target_port = 9091
    }
  }
}

resource "kubernetes_config_map_v1" "dashboards" {
  metadata {
    name      = "higayon-dashboards"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  data = { for name in fileset("${path.module}/../../monitoring/dashboards", "*.json") :
    name => file("${path.module}/../../monitoring/dashboards/${name}")
  }
}
