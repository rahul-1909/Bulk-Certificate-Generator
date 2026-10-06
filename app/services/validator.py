"""Validation services for certificate recipient data."""

from typing import Optional, Set, Tuple
from email_validator import EmailNotValidError, validate_email
from app.schemas.job import RecipientInput

MAX_STRING_LENGTH = 255
MAX_SCORE_LENGTH = 100


def validate_recipient(
    recipient: RecipientInput,
    seen_emails: Set[str],
) -> Tuple[bool, Optional[str]]:
    """Validate a single recipient against business rules.

    Checks:
    1. Non-blank name.
    2. Non-blank email.
    3. String length bounds (name, email, role, score).
    4. Valid email address syntax.
    5. Duplicate email within the current request batch.

    Returns:
        (True, None) if valid.
        (False, error_reason) if invalid.
    """
    # 1. Blank or missing name check
    if not recipient.name or not recipient.name.strip():
        return False, "Recipient name cannot be blank."

    # 2. Blank or missing email check
    if not recipient.email or not recipient.email.strip():
        return False, "Recipient email cannot be blank."

    # 3. Over-long string limits
    if len(recipient.name) > MAX_STRING_LENGTH:
        return False, f"Recipient name exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if len(recipient.email) > MAX_STRING_LENGTH:
        return False, f"Email exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if recipient.role and len(recipient.role) > MAX_STRING_LENGTH:
        return False, f"Role exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if recipient.score and len(str(recipient.score)) > MAX_SCORE_LENGTH:
        return False, f"Score exceeds maximum allowed length ({MAX_SCORE_LENGTH} characters)."

    # 4. Email format validation
    stripped_email = recipient.email.strip()
    try:
        validated = validate_email(stripped_email, check_deliverability=False)
        normalized_email = validated.normalized.lower()
    except EmailNotValidError as exc:
        return False, f"Invalid email address: {str(exc)}"

    # 5. Duplicate email check within the request batch (case-insensitive)
    if normalized_email in seen_emails:
        return False, f"Duplicate email address '{recipient.email}' within this request batch."

    # Record email to prevent future duplicates in the batch
    seen_emails.add(normalized_email)

    return True, None
