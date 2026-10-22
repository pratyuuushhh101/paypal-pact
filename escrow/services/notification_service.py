"""Transactional notification service for escrow lifecycle state transitions."""

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import send_mail

if TYPE_CHECKING:
    from escrow.models import Pact

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatches transactional email notifications to buyers and sellers across the Pact lifecycle."""

    @staticmethod
    def _render_email_template(
        headline: str,
        badge_text: str,
        badge_bg: str,
        badge_color: str,
        rows: list[tuple[str, str]],
        message_box: str | None = None,
        footer_note: str | None = None,
    ) -> str:
        """Render a clean, modern dark-themed HTML email template with inline styles."""
        rows_html: str = "".join(
            f"""
            <tr>
              <td style="padding: 8px 0; color: #94a3b8; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">{label}</td>
              <td style="padding: 8px 0; color: #f8fafc; font-size: 13px; font-weight: 600; text-align: right; font-family: 'SF Mono', Consolas, Monaco, monospace;">{value}</td>
            </tr>
            """
            for label, value in rows
        )

        message_html: str = ""
        if message_box:
            message_html = f"""
            <div style="margin-top: 16px; padding: 14px; background-color: #0f172a; border-left: 3px solid {badge_color}; border-radius: 6px;">
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: {badge_color}; margin-bottom: 4px;">Details / Feedback</div>
              <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">{message_box}</div>
            </div>
            """

        footer_html: str = ""
        if footer_note:
            footer_html = f"""
            <p style="margin-top: 20px; font-size: 12px; color: #64748b; line-height: 1.5; text-align: center;">
              {footer_note}
            </p>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{headline}</title>
</head>
<body style="margin: 0; padding: 24px 12px; background-color: #020617; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 560px; margin: 0 auto; background-color: #0b0f19; border: 1px solid #1e293b; border-radius: 14px; overflow: hidden;">
    <!-- Header -->
    <tr>
      <td style="padding: 24px 28px 16px 28px; border-bottom: 1px solid #1e293b;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <span style="font-size: 18px; font-weight: 800; letter-spacing: -0.02em; color: #10b981;">PACT</span>
              <span style="font-size: 14px; color: #64748b; margin-left: 6px; font-weight: 500;">Escrow Protocol</span>
            </td>
            <td style="text-align: right;">
              <span style="display: inline-block; padding: 4px 10px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-radius: 9999px; background-color: {badge_bg}; color: {badge_color}; border: 1px solid {badge_color}33;">
                {badge_text}
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Body -->
    <tr>
      <td style="padding: 28px;">
        <h1 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em;">
          {headline}
        </h1>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top: 12px; border-collapse: collapse;">
          {rows_html}
        </table>

        {message_html}

        {footer_html}
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 16px 28px; background-color: #050811; border-top: 1px solid #1e293b; text-align: center;">
        <p style="margin: 0; font-size: 11px; color: #475569;">
          Automated message from Pact Autonomous Escrow Engine. Do not reply directly to this email.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""

    def _send_email(
        self,
        subject: str,
        plain_text: str,
        recipient_list: list[str],
        html_message: str | None = None,
    ) -> bool:
        """Send an email safely without throwing exceptions or crashing caller."""
        valid_recipients = [r.strip() for r in recipient_list if r and isinstance(r, str) and "@" in r]
        if not valid_recipients:
            logger.warning("NotificationService: No valid recipients for email subject '%s'", subject)
            return False

        from_email: str = getattr(settings, "DEFAULT_FROM_EMAIL", "notifications@pact-escrow.com")

        try:
            send_mail(
                subject=subject,
                message=plain_text,
                from_email=from_email,
                recipient_list=valid_recipients,
                fail_silently=True,
                html_message=html_message,
            )
            logger.info("Notification sent successfully to %s: '%s'", valid_recipients, subject)
            return True
        except Exception as exc:
            logger.exception("NotificationService: Failed to send email to %s: %s", valid_recipients, exc)
            return False

    def send_authorization_notice(self, pact: "Pact") -> bool:
        """Notify buyer that funds are safely held in escrow."""
        buyer_email: str | None = getattr(getattr(pact, "buyer", None), "email", None)
        if not buyer_email:
            logger.warning("send_authorization_notice: Pact %s has no buyer email.", pact.id)
            return False

        subject = f"[Pact Escrow] Funds Authorized - Pact #{pact.id}"
        plain_text = (
            f"Hello,\n\n"
            f"Your funds of {pact.amount} {pact.currency} have been successfully authorized and held in escrow.\n\n"
            f"Pact ID: {pact.id}\n"
            f"Amount: {pact.amount} {pact.currency}\n"
            f"Deliverable Format: {pact.deliverable_type}\n"
            f"Status: AUTHORIZED (Funds in Escrow)\n\n"
            f"The seller can now begin work. Funds remain locked in escrow until the deliverable is validated "
            f"by the Groq AI verification engine.\n\n"
            f"Best regards,\nPact Escrow Team"
        )

        html = self._render_email_template(
            headline="Funds Authorized & Escrow Active",
            badge_text="FUNDS LOCKED",
            badge_bg="#064e3b",
            badge_color="#10b981",
            rows=[
                ("Pact ID", str(pact.id)),
                ("Escrow Total", f"{pact.amount} {pact.currency}"),
                ("Deliverable", pact.deliverable_type),
                ("Lifecycle State", "AUTHORIZED"),
            ],
            footer_note="Your funds are securely held via PayPal authorization and will only release once delivery criteria are met.",
        )

        return self._send_email(subject, plain_text, [buyer_email], html)

    def send_submission_notice(self, pact: "Pact") -> bool:
        """Notify buyer that seller has submitted work and AI verification has begun."""
        buyer_email: str | None = getattr(getattr(pact, "buyer", None), "email", None)
        if not buyer_email:
            logger.warning("send_submission_notice: Pact %s has no buyer email.", pact.id)
            return False

        subject = f"[Pact Escrow] Deliverable Submitted - Pact #{pact.id}"
        plain_text = (
            f"Hello,\n\n"
            f"The seller has submitted a deliverable for your contract (Attempt {pact.current_attempt} of {pact.max_attempts}).\n\n"
            f"Pact ID: {pact.id}\n"
            f"Deliverable Type: {pact.deliverable_type}\n"
            f"Attempt: {pact.current_attempt}/{pact.max_attempts}\n"
            f"Status: SUBMITTED (Verification In Progress)\n\n"
            f"Automated AI verification is currently running to evaluate quality criteria and safety guidelines.\n\n"
            f"Best regards,\nPact Escrow Team"
        )

        html = self._render_email_template(
            headline="Deliverable Submitted for Verification",
            badge_text=f"ATTEMPT {pact.current_attempt}/{pact.max_attempts}",
            badge_bg="#0c4a6e",
            badge_color="#38bdf8",
            rows=[
                ("Pact ID", str(pact.id)),
                ("Attempt", f"{pact.current_attempt} of {pact.max_attempts}"),
                ("Deliverable Type", pact.deliverable_type),
                ("Status", "SUBMITTED"),
            ],
            footer_note="Groq AI Judge is analyzing the submission for schema integrity, buyer rubrics, and injection risks.",
        )

        return self._send_email(subject, plain_text, [buyer_email], html)

    def send_revision_requested_notice(self, pact: "Pact", reason: str, attempt: int) -> bool:
        """Notify seller with AI review feedback and remaining retry attempts."""
        seller_email: str | None = getattr(getattr(pact, "seller", None), "email", None)
        if not seller_email:
            logger.warning("send_revision_requested_notice: Pact %s has no seller email.", pact.id)
            return False

        attempts_remaining = max(0, pact.max_attempts - attempt)
        subject = f"[Pact Escrow] Revision Requested - Pact #{pact.id} (Attempt {attempt} of {pact.max_attempts})"
        flags_str = ", ".join(pact.last_rejection_flags) if pact.last_rejection_flags else "None"

        plain_text = (
            f"Hello,\n\n"
            f"The AI judge reviewed your deliverable for Pact #{pact.id} and has requested revisions.\n\n"
            f"Pact ID: {pact.id}\n"
            f"Attempt: {attempt} of {pact.max_attempts}\n"
            f"Remaining Attempts: {attempts_remaining}\n"
            f"Status: REVISION REQUESTED\n\n"
            f"AI Evaluation Feedback:\n{reason}\n\n"
            f"Flagged Items: {flags_str}\n\n"
            f"Escrow funds ({pact.amount} {pact.currency}) remain locked in escrow. "
            f"Please address the feedback and resubmit your deliverable.\n\n"
            f"Best regards,\nPact Escrow Team"
        )

        html = self._render_email_template(
            headline="Action Required: Revision Requested",
            badge_text=f"{attempts_remaining} RETRY REMAINING" if attempts_remaining == 1 else f"{attempts_remaining} RETRIES REMAINING",
            badge_bg="#78350f",
            badge_color="#f59e0b",
            rows=[
                ("Pact ID", str(pact.id)),
                ("Submission Attempt", f"{attempt} of {pact.max_attempts}"),
                ("Flagged Issues", flags_str),
                ("Escrow Protection", f"{pact.amount} {pact.currency} (Held)"),
            ],
            message_box=reason,
            footer_note="Your funds remain reserved. Review the rejection rationale above and resubmit the dataset.",
        )

        return self._send_email(subject, plain_text, [seller_email], html)

    def send_resolution_notice(self, pact: "Pact", state: str, reason: str) -> bool:
        """Notify participants of contract resolution.

        - On CAPTURED: Notifies seller of funds release and buyer of completed contract.
        - On VOIDED (or REJECTED): Notifies buyer that escrow hold was voided and refunded.
        """
        buyer_email: str | None = getattr(getattr(pact, "buyer", None), "email", None)
        seller_email: str | None = getattr(getattr(pact, "seller", None), "email", None)

        sent_any: bool = False

        if state == "CAPTURED":
            # 1. Notify Buyer of completion
            if buyer_email:
                b_subject = f"[Pact Escrow] Contract Completed & Funds Released - Pact #{pact.id}"
                b_plain = (
                    f"Hello,\n\n"
                    f"Great news! The deliverable for Pact #{pact.id} has passed all AI verification criteria.\n\n"
                    f"Pact ID: {pact.id}\n"
                    f"Amount: {pact.amount} {pact.currency}\n"
                    f"Status: CAPTURED\n"
                    f"Evaluation Summary: {reason}\n\n"
                    f"Escrow funds have been captured and released to the seller. Your verified deliverable "
                    f"is available in the dashboard.\n\n"
                    f"Best regards,\nPact Escrow Team"
                )
                b_html = self._render_email_template(
                    headline="Contract Completed & Deliverable Verified",
                    badge_text="COMPLETED",
                    badge_bg="#064e3b",
                    badge_color="#10b981",
                    rows=[
                        ("Pact ID", str(pact.id)),
                        ("Total Paid", f"{pact.amount} {pact.currency}"),
                        ("Deliverable", pact.deliverable_type),
                        ("Status", "CAPTURED"),
                    ],
                    message_box=f"AI Evaluation: {reason}",
                    footer_note="The seller has fulfilled all specifications. Deliverable dataset is now available.",
                )
                if self._send_email(b_subject, b_plain, [buyer_email], b_html):
                    sent_any = True

            # 2. Notify Seller of payment release
            if seller_email:
                s_subject = f"[Pact Escrow] Payment Released! - Pact #{pact.id}"
                s_plain = (
                    f"Hello,\n\n"
                    f"Congratulations! Your deliverable for Pact #{pact.id} has successfully passed AI verification.\n\n"
                    f"Pact ID: {pact.id}\n"
                    f"Amount Released: {pact.amount} {pact.currency}\n"
                    f"Status: CAPTURED\n\n"
                    f"Payment has been captured and released to your account.\n\n"
                    f"Best regards,\nPact Escrow Team"
                )
                s_html = self._render_email_template(
                    headline="Escrow Payout Released!",
                    badge_text="FUNDS RELEASED",
                    badge_bg="#064e3b",
                    badge_color="#10b981",
                    rows=[
                        ("Pact ID", str(pact.id)),
                        ("Payout Released", f"{pact.amount} {pact.currency}"),
                        ("Verification", "PASSED"),
                        ("Status", "CAPTURED"),
                    ],
                    message_box="Deliverable verified successfully. Funds have been captured and disbursed.",
                    footer_note="Thank you for fulfilling this contract through the Pact Autonomous Escrow Protocol.",
                )
                if self._send_email(s_subject, s_plain, [seller_email], s_html):
                    sent_any = True

        else:
            # VOIDED / REJECTED: Notify Buyer of refund
            if buyer_email:
                subject = f"[Pact Escrow] Escrow Hold Voided & Refunded - Pact #{pact.id}"
                plain = (
                    f"Hello,\n\n"
                    f"The escrow hold for Pact #{pact.id} has been voided and your funds released back to you.\n\n"
                    f"Pact ID: {pact.id}\n"
                    f"Amount: {pact.amount} {pact.currency}\n"
                    f"Status: {state}\n"
                    f"Reason: {reason}\n\n"
                    f"The PayPal authorization hold on {pact.amount} {pact.currency} was released. "
                    f"No funds were captured from your account.\n\n"
                    f"Best regards,\nPact Escrow Team"
                )
                html = self._render_email_template(
                    headline="Escrow Hold Voided & Refunded",
                    badge_text="HOLD VOIDED",
                    badge_bg="#4c0519",
                    badge_color="#f43f5e",
                    rows=[
                        ("Pact ID", str(pact.id)),
                        ("Released Amount", f"{pact.amount} {pact.currency}"),
                        ("Final State", state),
                    ],
                    message_box=f"Resolution Reason: {reason}",
                    footer_note="The escrow authorization has been safely terminated. No charges were captured.",
                )
                if self._send_email(subject, plain, [buyer_email], html):
                    sent_any = True

            # Also notify seller if present
            if seller_email:
                s_subject = f"[Pact Escrow] Contract Concluded - Pact #{pact.id}"
                s_plain = (
                    f"Hello,\n\n"
                    f"Pact #{pact.id} has been concluded with state '{state}'.\n\n"
                    f"Pact ID: {pact.id}\n"
                    f"Status: {state}\n"
                    f"Reason: {reason}\n\n"
                    f"Best regards,\nPact Escrow Team"
                )
                s_html = self._render_email_template(
                    headline=f"Contract {state.capitalize()}",
                    badge_text=state,
                    badge_bg="#334155",
                    badge_color="#94a3b8",
                    rows=[
                        ("Pact ID", str(pact.id)),
                        ("Final State", state),
                    ],
                    message_box=reason,
                    footer_note="This contract is closed and cannot be resubmitted.",
                )
                if self._send_email(s_subject, s_plain, [seller_email], s_html):
                    sent_any = True

        return sent_any


# Singleton convenience instance
notification_service: NotificationService = NotificationService()
