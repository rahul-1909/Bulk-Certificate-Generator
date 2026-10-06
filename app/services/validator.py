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
    2. String length bounds (name, email, role, score).
    3. Valid email address syntax.
    4. Duplicate email within the current request batch.

    Returns:
        (True, None) if valid.
        (False, error_reason) if invalid.
    """
    # 1. Blank name check
    if not recipient.name or not recipient.name.strip():
        return False, "Recipient name cannot be blank."

    # 2. Over-long string limits
    if len(recipient.name) > MAX_STRING_LENGTH:
        return False, f"Recipient name exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if len(recipient.email) > MAX_STRING_LENGTH:
        return False, f"Email exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if recipient.role and len(recipient.role) > MAX_STRING_LENGTH:
        return False, f"Role exceeds maximum allowed length ({MAX_STRING_LENGTH} characters)."

    if recipient.score and len(recipient.score) > MAX_SCORE_LENGTH:
        return False, f"Score exceeds maximum allowed length ({MAX_SCORE_LENGTH} characters)."

    # 3. Email format validation
    stripped_email = recipient.email.strip()
    try:
        validated = validate_email(stripped_email, check_deliverability=False)
        normalized_email = validated.normalized.lower()
    except (EmailNotValidError, Exception) as exc:
        return False, f"Invalid email address: {str(exc)}"

    # 4. Duplicate email check within the request batch
    if normalized_email in seen_emails:
        return False, f"Duplicate email address '{recipient.email}' within this request batch."

    # Record email to prevent future duplicates in the batch
    seen_emails.add(normalized_email)

    return True, None


def is_eligible_for_generation(
    name: str,
    email: str,
    role: Optional[str] = None,
    score: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if recipient attributes meet basic validity criteria to attempt PDF generation.

    Distinguishes permanent validation failures (e.g. blank name or malformed email)
    from transient system errors.
    """
    if not name or not name.strip():
        return False, "Recipient name cannot be blank."
    if len(name) > MAX_STRING_LENGTH:
        return False, f"Recipient name exceeds {MAX_STRING_LENGTH} characters."
    if not email or len(email) > MAX_STRING_LENGTH:
        return False, f"Email exceeds {MAX_STRING_LENGTH} characters."
    if role and len(role) > MAX_STRING_LENGTH:
        return False, f"Role exceeds {MAX_STRING_LENGTH} characters."
    if score and len(score) > MAX_SCORE_LENGTH:
        return False, f"Score exceeds {MAX_SCORE_LENGTH} characters."
    try:
        validate_email(email.strip(), check_deliverability=False)
    except Exception as exc:
        return False, f"Invalid email address: {str(exc)}"
    return True, None
