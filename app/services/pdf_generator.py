"""PDF Certificate generation service using ReportLab."""

import os
import re
from pathlib import Path
from typing import Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from app.core.config import get_settings


def sanitize_filename(name: str) -> str:
    """Sanitize recipient name to prevent path traversal and filesystem issues.

    Replaces non-alphanumeric characters (except dashes and underscores) with underscores
    and trims excess characters.
    """
    cleaned = re.sub(r"[^\w\-]", "_", name.strip())
    # Collapse consecutive underscores
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "recipient"
    return cleaned[:60]


def _fit_font_size(
    pdf: canvas.Canvas,
    text: str,
    font_name: str,
    initial_size: int,
    min_size: int,
    max_width: float,
) -> int:
    """Dynamically scale down font size until text fits within max_width."""
    size = initial_size
    while size > min_size and pdf.stringWidth(text, font_name, size) > max_width:
        size -= 1
    return size


def _fit_text_to_width(
    pdf: canvas.Canvas,
    text: str,
    font_name: str,
    font_size: int,
    max_width: float,
) -> str:
    """Truncate text with ellipsis if it still exceeds max_width at the minimum font size."""
    if pdf.stringWidth(text, font_name, font_size) <= max_width:
        return text
    truncated = text
    while len(truncated) > 3 and pdf.stringWidth(truncated + "...", font_name, font_size) > max_width:
        truncated = truncated[:-1]
    return truncated + "..."


def generate_certificate_pdf(
    recipient_id: str,
    recipient_name: str,
    title: str,
    issuer: str,
    issue_date: str,
    role: Optional[str] = None,
    score: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> str:
    """Generate a high-quality certificate PDF from a predefined template.

    Args:
        recipient_id: Unique UUID string for the recipient.
        recipient_name: Name of the recipient to render prominently.
        title: Title of the course, training, or achievement.
        issuer: Organization or authority issuing the certificate.
        issue_date: Date of issuance.
        role: Optional role or distinction.
        score: Optional score or grade.
        output_dir: Directory to save the PDF (defaults to settings.storage_path).

    Returns:
        The absolute filesystem path to the created PDF file.

    Raises:
        ValueError: If path traversal is detected or parameters are invalid.
    """
    settings = get_settings()
    target_dir = (output_dir or settings.storage_path).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(recipient_name)
    filename = f"{recipient_id}_{safe_name}.pdf"
    file_path = (target_dir / filename).resolve()

    # Security check: guarantee file resides within target directory (no traversal)
    if not file_path.is_relative_to(target_dir):
        raise ValueError("Invalid filename: path traversal attempt detected.")

    # A4 Landscape dimensions in points (841.89 x 595.27)
    width, height = landscape(A4)
    max_text_width = width - 160

    pdf = canvas.Canvas(str(file_path), pagesize=landscape(A4))
    pdf.setTitle(f"Certificate - {recipient_name}")
    pdf.setSubject(title)
    pdf.setAuthor(issuer)

    # 1. Background fill
    pdf.setFillColor(colors.HexColor("#FAFBFD"))
    pdf.rect(0, 0, width, height, stroke=0, fill=1)

    # 2. Elegant double borders
    # Outer navy border
    pdf.setStrokeColor(colors.HexColor("#0F294A"))
    pdf.setLineWidth(3.5)
    pdf.rect(28, 28, width - 56, height - 56)

    # Inner gold border
    pdf.setStrokeColor(colors.HexColor("#D69E2E"))
    pdf.setLineWidth(1.5)
    pdf.rect(36, 36, width - 72, height - 72)

    # Corner decorative accents
    for x in [36, width - 36]:
        for y in [36, height - 36]:
            pdf.setFillColor(colors.HexColor("#D69E2E"))
            pdf.circle(x, y, 4, stroke=0, fill=1)

    # 3. Header: Issuing organization (auto-scaled and bounded)
    issuer_font_size = _fit_font_size(pdf, issuer.upper(), "Helvetica-Bold", 12, 8, max_text_width)
    display_issuer_header = _fit_text_to_width(pdf, issuer.upper(), "Helvetica-Bold", issuer_font_size, max_text_width)
    pdf.setFillColor(colors.HexColor("#4A5568"))
    pdf.setFont("Helvetica-Bold", issuer_font_size)
    pdf.drawCentredString(width / 2, height - 85, display_issuer_header)

    # 4. Certificate Main Title
    pdf.setFillColor(colors.HexColor("#0F294A"))
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(width / 2, height - 130, "CERTIFICATE OF ACHIEVEMENT")

    # 5. Presentation line
    pdf.setFillColor(colors.HexColor("#718096"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, height - 170, "THIS CERTIFICATE IS PROUDLY PRESENTED TO")

    # 6. Recipient Name (auto-scaled to fit landscape bounds without overflow)
    name_font_size = _fit_font_size(pdf, recipient_name, "Helvetica-Bold", 26, 12, max_text_width)
    display_name = _fit_text_to_width(pdf, recipient_name, "Helvetica-Bold", name_font_size, max_text_width)
    pdf.setFillColor(colors.HexColor("#1A202C"))
    pdf.setFont("Helvetica-Bold", name_font_size)
    pdf.drawCentredString(width / 2, height - 220, display_name)

    # Underline below recipient name
    name_width = pdf.stringWidth(display_name, "Helvetica-Bold", name_font_size)
    line_start = (width - min(name_width + 40, width - 200)) / 2
    line_end = line_start + min(name_width + 40, width - 200)
    pdf.setStrokeColor(colors.HexColor("#D69E2E"))
    pdf.setLineWidth(2)
    pdf.line(line_start, height - 232, line_end, height - 232)

    # 7. Achievement description & title (auto-scaled to fit landscape bounds)
    pdf.setFillColor(colors.HexColor("#4A5568"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(
        width / 2,
        height - 265,
        "for successfully completing the requirements and demonstrating excellence in",
    )

    title_font_size = _fit_font_size(pdf, title, "Helvetica-Bold", 18, 9, max_text_width)
    display_title = _fit_text_to_width(pdf, title, "Helvetica-Bold", title_font_size, max_text_width)
    pdf.setFillColor(colors.HexColor("#1E3A8A"))
    pdf.setFont("Helvetica-Bold", title_font_size)
    pdf.drawCentredString(width / 2, height - 295, display_title)

    # 8. Optional distinctions (Role and/or Score, auto-scaled to fit bounds)
    extra_details = []
    if role:
        extra_details.append(f"Role: {role}")
    if score:
        extra_details.append(f"Score: {score}")

    if extra_details:
        details_text = "  |  ".join(extra_details)
        details_font_size = _fit_font_size(pdf, details_text, "Helvetica-Oblique", 11, 8, max_text_width)
        display_details = _fit_text_to_width(pdf, details_text, "Helvetica-Oblique", details_font_size, max_text_width)
        pdf.setFillColor(colors.HexColor("#2D3748"))
        pdf.setFont("Helvetica-Oblique", details_font_size)
        pdf.drawCentredString(width / 2, height - 330, display_details)

    # 9. Footer: Left side (Date & Certificate ID)
    pdf.setFillColor(colors.HexColor("#4A5568"))
    pdf.setFont("Helvetica", 10)
    pdf.drawString(60, 110, f"Date of Issue: {issue_date}")
    pdf.setFillColor(colors.HexColor("#718096"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(60, 92, f"Certificate ID: {recipient_id}")

    # 10. Footer: Right side (Authorized Signatory)
    sig_line_x = width - 260
    pdf.setStrokeColor(colors.HexColor("#A0AEC0"))
    pdf.setLineWidth(1)
    pdf.line(sig_line_x, 115, sig_line_x + 190, 115)

    sig_font_size = _fit_font_size(pdf, issuer, "Helvetica-Bold", 10, 7, 180)
    display_sig = _fit_text_to_width(pdf, issuer, "Helvetica-Bold", sig_font_size, 180)
    pdf.setFillColor(colors.HexColor("#1A202C"))
    pdf.setFont("Helvetica-Bold", sig_font_size)
    pdf.drawCentredString(sig_line_x + 95, 98, display_sig)
    pdf.setFillColor(colors.HexColor("#718096"))
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(sig_line_x + 95, 84, "Authorized Representative")

    # Finalize PDF
    pdf.showPage()
    pdf.save()

    return str(file_path)
