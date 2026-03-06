"""
Email service module.
Supports multiple providers:
1. mail.chatgpt.org.uk (default)
2. Self-hosted Cloudflare Worker for custom domain inboxes
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import email
import random
import re
import string
import time
from email import policy
from typing import Dict, List, Optional, Tuple

from config import (
    EMAIL_PROVIDER,
    EMAIL_WORKER_URL,
    EMAIL_DOMAIN,
    EMAIL_PREFIX_LENGTH,
    EMAIL_WAIT_TIMEOUT,
    EMAIL_POLL_INTERVAL,
    EMAIL_ADMIN_PASSWORD,
    EMAIL_WORKER_AUTH_HEADER,
    HTTP_TIMEOUT,
)
from helpers.utils import build_request_user_agent, http_session


def parse_raw_email(raw_content: str) -> Dict[str, str]:
    """Parse RFC822 raw email content into minimal fields."""
    result = {"subject": "", "body": "", "sender": ""}
    if not raw_content:
        return result

    try:
        msg = email.message_from_string(raw_content, policy=policy.default)
        result["subject"] = msg.get("Subject", "")
        result["sender"] = msg.get("From", "")

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ["text/plain", "text/html"]:
                    payload = part.get_payload(decode=True)
                    if payload:
                        result["body"] = payload.decode("utf-8", errors="ignore")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                result["body"] = payload.decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"  Parse raw email failed: {exc}")

    return result


class _CodeExtractorMixin:
    """Shared verification code extraction logic."""

    @staticmethod
    def _mail_id(mail: Dict) -> Optional[str]:
        for key in ("id", "messageId", "message_id", "mail_id"):
            if mail.get(key):
                return str(mail[key])

        subject = str(mail.get("subject", ""))
        sender = str(mail.get("from", "") or mail.get("sender", ""))
        date = str(mail.get("date", "") or mail.get("created_at", ""))
        if subject or sender:
            return f"{sender}|{subject}|{date}"
        return None

    def extract_code_from_email(self, email_data: Dict) -> Optional[str]:
        subject = str(email_data.get("subject", "") or "")
        sender = str(email_data.get("from", "") or email_data.get("sender", "") or "")

        text_parts = [
            str(email_data.get("content", "") or ""),
            str(email_data.get("text", "") or ""),
            str(email_data.get("text_content", "") or ""),
            str(email_data.get("body", "") or ""),
        ]
        html = str(email_data.get("html", "") or email_data.get("html_content", "") or "")

        raw = str(email_data.get("raw", "") or "")
        if raw and not any(text_parts):
            parsed = parse_raw_email(raw)
            if not subject:
                subject = parsed.get("subject", "")
            if not sender:
                sender = parsed.get("sender", "")
            text_parts.append(parsed.get("body", ""))

        searchable = "\n".join([subject, sender, html, *text_parts])

        patterns = [
            r"[Vv]erification\s+code[:\s-]+([0-9]{6})",
            r"\b([0-9]{6})\b",
            r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, searchable, re.IGNORECASE)
            if match:
                return match.group(1)

        return None


class ChatGPTMailClient(_CodeExtractorMixin):
    """Client for mail.chatgpt.org.uk temporary mailbox API."""

    def __init__(self):
        self.base_url = "https://mail.chatgpt.org.uk/api"
        self.current_email: Optional[str] = None
        self.processed_mail_ids = set()

    @staticmethod
    def _base_headers() -> Dict[str, str]:
        return {
            "User-Agent": build_request_user_agent(),
            "Origin": "https://mail.chatgpt.org.uk",
            "Referer": "https://mail.chatgpt.org.uk/",
        }

    def generate_email(self) -> Optional[str]:
        try:
            response = http_session.get(
                f"{self.base_url}/generate-email",
                headers={**self._base_headers(), "Content-Type": "application/json"},
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                print(f"Email API error: HTTP {response.status_code}")
                return None

            result = response.json()
            address = result.get("data", {}).get("email") if result.get("success") else None
            if not address:
                print(f"Email API returned invalid payload: {result}")
                return None

            self.current_email = address
            self.processed_mail_ids.clear()

            # Snapshot existing messages so only new emails are processed.
            for mail in self.fetch_emails(address):
                mail_id = self._mail_id(mail)
                if mail_id:
                    self.processed_mail_ids.add(mail_id)

            return address
        except Exception as exc:
            print(f"Create temp mailbox failed: {exc}")
            return None

    def fetch_emails(self, email_address: Optional[str] = None) -> List[Dict]:
        target = email_address or self.current_email
        if not target:
            return []

        try:
            timestamp = int(time.time() * 1000)
            response = http_session.get(
                f"{self.base_url}/emails?email={target}&_t={timestamp}",
                headers={
                    **self._base_headers(),
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                return []

            result = response.json()
            if not result.get("success"):
                return []

            return result.get("data", {}).get("emails", []) or []
        except Exception as exc:
            print(f"Fetch emails failed: {exc}")
            return []

    def wait_for_code(self, email_address: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        target = email_address or self.current_email
        if not target:
            print("No mailbox specified")
            return None

        print(f"Listening mailbox: {target}")
        start_time = time.time()
        poll_interval = max(1, EMAIL_POLL_INTERVAL)

        while time.time() - start_time < timeout:
            for mail in self.fetch_emails(target):
                mail_id = self._mail_id(mail)
                if mail_id and mail_id in self.processed_mail_ids:
                    continue
                if mail_id:
                    self.processed_mail_ids.add(mail_id)

                code = self.extract_code_from_email(mail)
                if code:
                    return code

            time.sleep(poll_interval)

        return None

    # Compatibility with older call sites
    def get_verification_code(self, email_address: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        return self.wait_for_code(email_address=email_address, timeout=timeout)


class CloudflareDomainMailClient(_CodeExtractorMixin):
    """Client for a self-hosted Cloudflare Worker email API."""

    def __init__(self):
        self.base_url = EMAIL_WORKER_URL.rstrip("/")
        self.domain = EMAIL_DOMAIN
        self.admin_password = EMAIL_ADMIN_PASSWORD
        self.auth_header = EMAIL_WORKER_AUTH_HEADER or "X-Admin-Password"
        self.current_email: Optional[str] = None
        self.current_token: Optional[str] = None
        self.processed_mail_ids = set()

    def _admin_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": build_request_user_agent(),
        }
        if self.admin_password:
            headers[self.auth_header] = self.admin_password
        return headers

    @staticmethod
    def _token_headers(token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": build_request_user_agent(),
        }

    def create_address(self, prefix: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        local = prefix or "".join(
            random.choices(string.ascii_lowercase + string.digits, k=EMAIL_PREFIX_LENGTH)
        )

        try:
            response = http_session.post(
                f"{self.base_url}/api/new_address",
                headers=self._admin_headers(),
                json={"name": local, "domain": self.domain},
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                print(f"Cloudflare worker error: HTTP {response.status_code}")
                return None, None

            payload = response.json()
            address = payload.get("address") or payload.get("email")
            token = payload.get("jwt") or payload.get("token")
            if not address or not token:
                print(f"Cloudflare worker payload invalid: {payload}")
                return None, None

            self.current_email = address
            self.current_token = token
            self.processed_mail_ids.clear()

            for mail in self.fetch_emails(token):
                mail_id = self._mail_id(mail)
                if mail_id:
                    self.processed_mail_ids.add(mail_id)

            return address, token
        except Exception as exc:
            print(f"Create Cloudflare mailbox failed: {exc}")
            return None, None

    def fetch_emails(self, token: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        try:
            response = http_session.get(
                f"{self.base_url}/api/mails?limit={limit}&offset={offset}",
                headers=self._token_headers(token),
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                return []

            payload = response.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("results") or payload.get("mails") or payload.get("items") or []
            return []
        except Exception as exc:
            print(f"Fetch Cloudflare mails failed: {exc}")
            return []

    def get_email_detail(self, token: str, email_id: str) -> Optional[Dict]:
        try:
            response = http_session.get(
                f"{self.base_url}/api/mails/{email_id}",
                headers=self._token_headers(token),
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                return None
            detail = response.json()
            return detail if isinstance(detail, dict) else None
        except Exception as exc:
            print(f"Fetch Cloudflare mail detail failed: {exc}")
            return None

    def wait_for_code(self, token: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        active_token = token or self.current_token
        if active_token and "@" in active_token and self.current_email:
            if active_token.lower() == self.current_email.lower():
                active_token = self.current_token
        if not active_token:
            print("No worker mailbox token provided")
            return None

        start_time = time.time()
        poll_interval = max(1, EMAIL_POLL_INTERVAL)

        while time.time() - start_time < timeout:
            mails = self.fetch_emails(active_token)
            for mail in mails:
                mail_id = self._mail_id(mail)
                if mail_id and mail_id in self.processed_mail_ids:
                    continue
                if mail_id:
                    self.processed_mail_ids.add(mail_id)

                payload = mail
                detail_id = mail.get("id") or mail.get("messageId") or mail.get("message_id")
                has_content = any(
                    mail.get(k) for k in ("content", "text", "text_content", "body", "html", "html_content", "raw")
                )
                if detail_id and not has_content:
                    detail = self.get_email_detail(active_token, str(detail_id))
                    if detail:
                        payload = detail

                code = self.extract_code_from_email(payload)
                if code:
                    return code

            time.sleep(poll_interval)

        return None

    # Compatibility with older call sites
    def get_verification_code(self, token: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        return self.wait_for_code(token=token, timeout=timeout)


def _build_mail_client():
    provider = (EMAIL_PROVIDER or "chatgpt").strip().lower()
    if provider == "cloudflare_domain":
        return CloudflareDomainMailClient()
    if provider != "chatgpt":
        print(f"Unknown email provider '{EMAIL_PROVIDER}', fallback to chatgpt")
    return ChatGPTMailClient()


_mail_client = _build_mail_client()


def get_mail_client():
    """Return active global mail client based on config.email.provider."""
    return _mail_client


def create_temp_email() -> Tuple[Optional[str], Optional[str]]:
    """Create mailbox and return (email, token_or_email)."""
    if isinstance(_mail_client, CloudflareDomainMailClient):
        print("Creating temp mailbox via Cloudflare worker...")
        return _mail_client.create_address()

    print("Creating temp mailbox via mail.chatgpt.org.uk...")
    email_address = _mail_client.generate_email()
    if email_address:
        return email_address, email_address
    return None, None


def wait_for_verification_email(email_or_token: str, timeout: Optional[int] = None) -> Optional[str]:
    """Wait for verification email and return extracted code."""
    effective_timeout = timeout if timeout is not None else EMAIL_WAIT_TIMEOUT
    return _mail_client.wait_for_code(email_or_token, effective_timeout)


# Backward-compatible Cloudflare helper functions

def create_temp_email_cloudflare() -> Tuple[Optional[str], Optional[str]]:
    client = _mail_client if isinstance(_mail_client, CloudflareDomainMailClient) else CloudflareDomainMailClient()
    return client.create_address()


def fetch_emails_cloudflare(jwt_token: str):
    client = _mail_client if isinstance(_mail_client, CloudflareDomainMailClient) else CloudflareDomainMailClient()
    return client.fetch_emails(jwt_token)


def get_email_detail_cloudflare(jwt_token: str, email_id: str):
    client = _mail_client if isinstance(_mail_client, CloudflareDomainMailClient) else CloudflareDomainMailClient()
    return client.get_email_detail(jwt_token, email_id)
