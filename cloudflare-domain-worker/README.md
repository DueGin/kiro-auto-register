# Cloudflare Custom-Domain Mail Worker

This folder contains a Worker that receives emails for your own domain and exposes a polling API for the Python app.

## 1. Prerequisites

- Your domain is managed by Cloudflare.
- Email Routing is enabled for that domain.
- Wrangler is installed and authenticated (`npm i -g wrangler`, then `wrangler login`).

## 2. Create KV namespaces

Run inside this folder:

```bash
wrangler kv namespace create MAIL_KV
wrangler kv namespace create MAIL_KV --preview
```

Copy returned IDs into [wrangler.toml](./wrangler.toml):

- `id`
- `preview_id`

## 3. Configure vars and secret

Edit [wrangler.toml](./wrangler.toml):

- `MAIL_DOMAIN`: your receiving domain (for example `example.com`)
- TTL values if needed

Set admin password as secret:

```bash
wrangler secret put ADMIN_PASSWORD
```

## 4. Deploy

```bash
wrangler deploy
```

After deploy, note the Worker URL, for example:

- `https://domain-mail-worker.<subdomain>.workers.dev`

## 5. Email Routing rule

In Cloudflare dashboard for your domain, add an Email Routing rule:

- Recipient: `*@your-domain.com` (or a specific address)
- Action: `Send to Worker`
- Worker: `domain-mail-worker`

## 6. Python project config

Update [config/config.yaml](../config/config.yaml):

```yaml
email:
  provider: "cloudflare_domain"
  worker_url: "https://domain-mail-worker.<subdomain>.workers.dev"
  domain: "your-domain.com"
  admin_password: "your-admin-password"
  worker_auth_header: "X-Admin-Password"
```

## 7. API contract

- `POST /api/new_address`: create mailbox, returns `address` + `jwt`
- `GET /api/mails`: list emails with Bearer token
- `GET /api/mails/{id}`: email detail with Bearer token (`raw` included)