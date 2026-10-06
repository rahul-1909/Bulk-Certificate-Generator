"""Tests for PDF certificate rendering, metadata, text extraction, and path sanitization."""

import os
from pathlib import Path
import pypdf
import pytest
from app.services.pdf_generator import generate_certificate_pdf, sanitize_filename


def test_pdf_generation_content_and_structure(tmp_path: Path):
    """Verify generated certificate is a valid PDF, non-empty, starts with %PDF, and contains text."""
    recipient_id = "test-uuid-42"
    recipient_name = "Margaret Hamilton"
    title = "Apollo Guidance Computer Engineering"
    issuer = "NASA Software Division"
    issue_date = "2026-10-07"
    role = "Lead Flight Director"
    score = "100%"

    pdf_path = generate_certificate_pdf(
        recipient_id=recipient_id,
        recipient_name=recipient_name,
        title=title,
        issuer=issuer,
        issue_date=issue_date,
        role=role,
        score=score,
        output_dir=tmp_path,
    )

    # 1. File exists and is non-empty
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 500

    # 2. File starts with %PDF header
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header.startswith(b"%PDF")

    # 3. PDF reader parses and extracts text correctly
    reader = pypdf.PdfReader(pdf_path)
    assert len(reader.pages) == 1
    extracted_text = reader.pages[0].extract_text()

    assert recipient_name in extracted_text
    assert title in extracted_text
    assert issuer.upper() in extracted_text
    assert issue_date in extracted_text
    assert role in extracted_text
    assert score in extracted_text
    assert recipient_id in extracted_text


def test_filename_sanitization_prevents_path_traversal():
    """Verify that path traversal characters and directory delimiters are removed."""
    dirty_name_unix = "../../etc/passwd"
    sanitized_unix = sanitize_filename(dirty_name_unix)
    assert "/" not in sanitized_unix
    assert ".." not in sanitized_unix
    assert sanitized_unix == "etc_passwd"

    dirty_name_windows = "..\\..\\windows\\system32\\cmd.exe"
    sanitized_windows = sanitize_filename(dirty_name_windows)
    assert "\\" not in sanitized_windows
    assert ":" not in sanitized_windows
    assert sanitized_windows == "windows_system32_cmd_exe"

    blank_input = "   ...   "
    sanitized_blank = sanitize_filename(blank_input)
    assert sanitized_blank == "recipient"
