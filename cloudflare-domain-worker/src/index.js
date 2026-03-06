const DEFAULT_MESSAGE_TTL_SECONDS = 2 * 24 * 60 * 60;
const DEFAULT_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60;
const DEFAULT_MAX_MESSAGES_PER_INBOX = 200;

export default {
  async fetch(request, env) {
    return handleHttp(request, env);
  },

  async email(message, env) {
    await storeIncomingMail(message, env);
  },
};

async function handleHttp(request, env) {
  if (request.method === "OPTIONS") {
    return withCors(new Response(null, { status: 204 }));
  }

  const url = new URL(request.url);
  const path = normalizePath(url.pathname);

  if (path === "/health") {
    return json({ ok: true, service: "cloudflare-domain-mail-worker" });
  }

  if (path === "/api/new_address" && request.method === "POST") {
    if (!isAdminAuthorized(request, env)) {
      return json({ error: "unauthorized" }, 401);
    }

    let payload = {};
    try {
      payload = await request.json();
    } catch {
      // Keep empty payload for defaults.
    }

    const localPart = sanitizeLocalPart(payload.name);
    if (!localPart) {
      return json({ error: "invalid local part" }, 400);
    }

    const domain = String(payload.domain || env.MAIL_DOMAIN || "").trim().toLowerCase();
    if (!domain) {
      return json({ error: "MAIL_DOMAIN is required" }, 500);
    }

    const address = `${localPart}@${domain}`;
    const token = crypto.randomUUID().replace(/-/g, "");
    const tokenTtl = parsePositiveInt(env.TOKEN_TTL_SECONDS, DEFAULT_TOKEN_TTL_SECONDS);

    const tokenRecord = {
      address,
      created_at: new Date().toISOString(),
    };

    await env.MAIL_KV.put(tokenKey(token), JSON.stringify(tokenRecord), {
      expirationTtl: tokenTtl,
    });

    const existingInbox = (await env.MAIL_KV.get(inboxKey(address), { type: "json" })) || [];
    await env.MAIL_KV.put(inboxKey(address), JSON.stringify(Array.isArray(existingInbox) ? existingInbox : []), {
      expirationTtl: tokenTtl,
    });

    return json({
      address,
      jwt: token,
      token,
    });
  }

  if (path === "/api/mails" && request.method === "GET") {
    const auth = await authenticateToken(request, env);
    if (!auth.ok) {
      return json({ error: auth.error }, auth.status);
    }

    const limit = clamp(parsePositiveInt(url.searchParams.get("limit"), 20), 1, 100);
    const offset = Math.max(0, parsePositiveInt(url.searchParams.get("offset"), 0));

    const inbox = (await env.MAIL_KV.get(inboxKey(auth.address), { type: "json" })) || [];
    const safeInbox = Array.isArray(inbox) ? inbox : [];

    return json({
      total: safeInbox.length,
      mails: safeInbox.slice(offset, offset + limit),
    });
  }

  const mailDetailMatch = path.match(/^\/api\/mails\/([^/]+)$/);
  if (mailDetailMatch && request.method === "GET") {
    const auth = await authenticateToken(request, env);
    if (!auth.ok) {
      return json({ error: auth.error }, auth.status);
    }

    const id = decodeURIComponent(mailDetailMatch[1]);
    const detail = await env.MAIL_KV.get(mailKey(auth.address, id), { type: "json" });
    if (!detail) {
      return json({ error: "mail not found" }, 404);
    }

    return json(detail);
  }

  return json({ error: "not found" }, 404);
}

async function storeIncomingMail(message, env) {
  const to = normalizeAddress(message.to);
  const from = normalizeAddress(message.from);
  const configuredDomain = String(env.MAIL_DOMAIN || "").trim().toLowerCase();

  if (!to) {
    if (typeof message.setReject === "function") {
      message.setReject("Missing recipient");
    }
    return;
  }

  if (configuredDomain && !to.endsWith(`@${configuredDomain}`)) {
    if (typeof message.setReject === "function") {
      message.setReject(`Recipient domain not allowed: ${configuredDomain}`);
    }
    return;
  }

  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  const subject = message.headers.get("subject") || "";
  const date = message.headers.get("date") || createdAt;
  const messageId = message.headers.get("message-id") || "";
  const headers = Object.fromEntries(message.headers);

  let raw = "";
  try {
    const rawBuffer = await new Response(message.raw).arrayBuffer();
    raw = new TextDecoder("utf-8", { fatal: false }).decode(rawBuffer);
  } catch {
    raw = "";
  }

  const detail = {
    id,
    to,
    from,
    subject,
    date,
    message_id: messageId,
    created_at: createdAt,
    raw,
    headers,
  };

  const messageTtl = parsePositiveInt(env.MESSAGE_TTL_SECONDS, DEFAULT_MESSAGE_TTL_SECONDS);
  const maxMessages = parsePositiveInt(env.MAX_MESSAGES_PER_INBOX, DEFAULT_MAX_MESSAGES_PER_INBOX);

  await env.MAIL_KV.put(mailKey(to, id), JSON.stringify(detail), {
    expirationTtl: messageTtl,
  });

  const inbox = (await env.MAIL_KV.get(inboxKey(to), { type: "json" })) || [];
  const safeInbox = Array.isArray(inbox) ? inbox : [];

  const summary = {
    id,
    from,
    subject,
    date,
    created_at: createdAt,
  };

  safeInbox.unshift(summary);

  let trimmed = safeInbox;
  let deleted = [];
  if (safeInbox.length > maxMessages) {
    trimmed = safeInbox.slice(0, maxMessages);
    deleted = safeInbox.slice(maxMessages);
  }

  await env.MAIL_KV.put(inboxKey(to), JSON.stringify(trimmed), {
    expirationTtl: messageTtl,
  });

  if (deleted.length > 0) {
    await Promise.all(
      deleted
        .map((item) => item && item.id)
        .filter(Boolean)
        .map((mailId) => env.MAIL_KV.delete(mailKey(to, mailId))),
    );
  }
}

function normalizePath(pathname) {
  if (!pathname) return "/";
  const clean = pathname.replace(/\/+$/, "");
  return clean || "/";
}

function normalizeAddress(address) {
  if (!address) return "";
  return String(address).trim().toLowerCase().replace(/[<>]/g, "");
}

function sanitizeLocalPart(value) {
  const fallback = randomLocalPart();
  if (!value) return fallback;

  const normalized = String(value).trim().toLowerCase();
  if (!/^[a-z0-9._-]{1,64}$/.test(normalized)) {
    return "";
  }
  return normalized;
}

function randomLocalPart() {
  return `tmp${Math.random().toString(36).slice(2, 12)}`;
}

function tokenKey(token) {
  return `token:${token}`;
}

function inboxKey(address) {
  return `inbox:${address}`;
}

function mailKey(address, id) {
  return `mail:${address}:${id}`;
}

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function readBearerToken(request) {
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

async function authenticateToken(request, env) {
  const token = readBearerToken(request);
  if (!token) {
    return { ok: false, error: "missing bearer token", status: 401 };
  }

  const tokenData = await env.MAIL_KV.get(tokenKey(token), { type: "json" });
  if (!tokenData || !tokenData.address) {
    return { ok: false, error: "invalid token", status: 401 };
  }

  return {
    ok: true,
    token,
    address: normalizeAddress(tokenData.address),
  };
}

function isAdminAuthorized(request, env) {
  const expectedPassword = String(env.ADMIN_PASSWORD || "");
  if (!expectedPassword) {
    return true;
  }

  const headerName = String(env.ADMIN_AUTH_HEADER || "X-Admin-Password");
  const actual = request.headers.get(headerName) || "";
  return actual === expectedPassword;
}

function json(payload, status = 200) {
  const response = new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
  });
  return withCors(response);
}

function withCors(response) {
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Authorization,Content-Type,X-Admin-Password");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
