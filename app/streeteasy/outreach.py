from __future__ import annotations

import logging
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any, Awaitable, Callable

from .config import OutreachConfig, StreetEasySettings
from .matcher import format_listing_summary

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def build_outreach_message(
    node: dict[str, Any],
    url: str,
    outreach: OutreachConfig,
    details: dict[str, Any] | None = None,
) -> str:
    summary = format_listing_summary(node, url)
    dates = " or ".join(outreach.move_in_dates) if outreach.move_in_dates else "early August 2026"
    intro = outreach.custom_intro or (
        f"Hi,\n\nI'm {outreach.applicant_name or 'interested in renting'} and would like to "
        f"{'schedule a tour and ' if outreach.tour_request else ''}"
        f"learn more about the rental at {node.get('street', 'your listing')}."
    )
    body_parts = [
        intro,
        "",
        f"My preferred move-in: {dates}.",
    ]
    if outreach.income_note:
        body_parts.append(outreach.income_note)
    if outreach.applicant_phone:
        body_parts.append(f"Phone: {outreach.applicant_phone}")
    if outreach.applicant_email:
        body_parts.append(f"Email: {outreach.applicant_email}")
    body_parts.extend(
        [
            "",
            "Listing:",
            summary,
            "",
            "Thank you,",
            outreach.applicant_name or "Prospective tenant",
        ]
    )
    if details and details.get("rentalByListingId", {}).get("description"):
        desc = details["rentalByListingId"]["description"][:200]
        body_parts.insert(2, f"\n(From listing: {desc}...)\n")
    return "\n".join(body_parts)


async def draft_with_llm(
    llm_handler: Callable[[str], Awaitable[str]],
    node: dict[str, Any],
    url: str,
    outreach: OutreachConfig,
) -> str:
    base = build_outreach_message(node, url, outreach)
    prompt = (
        "Polish this broker outreach email to be professional, concise, and friendly. "
        "Keep facts accurate; do not invent details. Return only the email body.\n\n"
        f"{base}"
    )
    return await llm_handler(prompt)


def extract_broker_email(details: dict[str, Any] | None, description_fallback: str = "") -> str | None:
    text = description_fallback
    if details:
        rental = details.get("rentalByListingId") or {}
        text = (rental.get("description") or "") + " " + text
    matches = EMAIL_RE.findall(text)
    # Filter noreply / streeteasy addresses
    for email in matches:
        lower = email.lower()
        if "streeteasy" in lower or "noreply" in lower or "zillow" in lower:
            continue
        return email
    return None


def send_email_smtp(to_addr: str, subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM") or user
    if not all([host, user, password, from_addr]):
        raise RuntimeError("SMTP not configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    logger.info("Sent outreach email to %s", to_addr)


async def handle_outreach(
    settings: StreetEasySettings,
    node: dict[str, Any],
    url: str,
    listing_id: str,
    llm_handler: Callable[[str], Awaitable[str]] | None = None,
    details: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Run outreach per mode. Returns (status, message_text_for_telegram)."""
    mode = settings.outreach_mode
    outreach = settings.outreach
    summary = format_listing_summary(node, url)

    if mode == "notify":
        return "notified", f"New listing match:\n\n{summary}"

    message = build_outreach_message(node, url, outreach, details)
    if mode == "draft" and llm_handler:
        try:
            message = await draft_with_llm(llm_handler, node, url, outreach)
        except Exception:
            logger.exception("LLM draft failed, using template")

    if mode == "email":
        broker_email = extract_broker_email(
            details,
            (details or {}).get("rentalByListingId", {}).get("description", "") if details else "",
        )
        if broker_email and outreach.applicant_email:
            subject = f"Inquiry: {node.get('street', 'Rental')} — tour / Aug move-in"
            try:
                import asyncio

                await asyncio.to_thread(send_email_smtp, broker_email, subject, message)
                return "emailed", (
                    f"Emailed {broker_email}:\n\n{summary}\n\n--- Draft sent ---\n{message[:1200]}"
                )
            except Exception as e:
                logger.exception("Email send failed")
                return "email_failed", f"Match (email failed: {e}):\n\n{summary}\n\n--- Draft ---\n{message[:1200]}"

        return "draft_no_email", (
            f"Match (no broker email found — open StreetEasy to request tour):\n\n{summary}\n\n"
            f"--- Draft to send manually ---\n{message[:1200]}"
        )

    # draft mode default
    tour_note = (
        "\n\nOpen the listing link and tap Request a tour (StreetEasy requires a logged-in session)."
        if outreach.tour_request
        else ""
    )
    return "drafted", f"New match:\n\n{summary}\n\n--- Outreach draft ---\n{message[:1500]}{tour_note}"
