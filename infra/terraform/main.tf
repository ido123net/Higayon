terraform {
  required_version = ">= 1.6"
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
resource "kubernetes_job_v1" "migrate" {
  metadata {
    name      = "higayon-migrate-${var.release}"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  wait_for_completion = true
  spec {
    backoff_limit = 3
    template {
      metadata { labels = local.labels }
      spec {
        restart_policy = "Never"
        container {
          name    = "migrate"
          image   = var.image
          command = ["python", "manage.py", "migrate", "--noinput"]
          env_from {
            config_map_ref { name = kubernetes_config_map_v1.app.metadata[0].name }
          }
          env_from {
            secret_ref { name = var.runtime_secret_name }
          }
          resources {
            requests = var.resource_requests
            limits   = var.resource_limits
          }
        }
      }
    }
  }
  timeouts { create = "10m" }
}
resource "kubernetes_deployment_v1" "app" {
  depends_on = [kubernetes_job_v1.migrate]
  metadata {
    name      = "higayon"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  spec {
    replicas = var.replicas
    selector { match_labels = local.labels }
    template {
      metadata { labels = local.labels }
      spec {
        container {
          name  = "app"
          image = var.image
          port { container_port = 8000 }
          port { container_port = 9091 }
          env {
            name  = "METRICS_PORT"
            value = "9091"
          }
          env {
            name  = "LIVE_SOLVING"
            value = tostring(var.live_solving)
          }
          env_from {
            config_map_ref { name = kubernetes_config_map_v1.app.metadata[0].name }
          }
          env_from {
            secret_ref { name = var.runtime_secret_name }
          }
          readiness_probe {
            http_get {
              path = "/health/ready/"
              port = 8000
              http_header {
                name  = "X-Forwarded-Proto"
                value = "https"
              }
              http_header {
                name  = "Host"
                value = var.hostname
              }
            }
          }
          liveness_probe {
            http_get {
              path = "/health/live/"
              port = 8000
              http_header {
                name  = "X-Forwarded-Proto"
                value = "https"
              }
              http_header {
                name  = "Host"
                value = var.hostname
              }
            }
          }
          resources {
            requests = var.resource_requests
            limits   = var.resource_limits
          }
          security_context {
            allow_privilege_escalation = false
            run_as_non_root            = true
            run_as_user                = 1000
            capabilities { drop = ["ALL"] }
          }
        }
      }
    }
  }
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
