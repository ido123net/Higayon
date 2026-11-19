hostname        = "crossword.example.com"
owner_email     = "owner@example.com"
allowed_emails  = ["owner@example.com", "friend@example.com"]
ingress_class   = "traefik"
tls_issuer_name = "letsencrypt-production"
# Secrets are existing Kubernetes resources, never Terraform values.
