output "tunnel_token" {
  description = "Operation-time token for the external Kubernetes Secret."
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.k3s.token
  sensitive   = true
}
