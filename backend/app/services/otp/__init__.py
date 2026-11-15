"""Multi-channel one-time-code verification (SMS, email, WhatsApp).

    otp_generator     codes from ``secrets``, HMAC-SHA256 hashes bound to the challenge and destination
    otp_rate_limiter  per destination, IP and session limits stored in the database (shared by all API processes)
    sms_provider / email_provider / whatsapp_provider
                      build the message for each channel and send it through the clinic's own account or the platform's
    otp_verifier      attempt counting, expiry, single use, constant-time comparison
    otp_service       start / resend / verify, the booking token and the check the booking API runs

Codes are never returned by the API and never written to logs.
"""
from app.services.otp.otp_service import OTPService, booking_verification_required, check_booking_token, load_policy

__all__ = ["OTPService", "booking_verification_required", "check_booking_token", "load_policy"]
