"""
AI-powered resume parser using Google Gemini.

Extracts text from PDF resumes and uses Gemini to produce a structured
JSON profile with skills, experience, education, and other key details.
Results are cached in the database by file hash to avoid redundant API calls.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from src.core.interfaces import ILLMProvider, IRepository, IResumeParser
from src.core.exceptions import LLMAPIError, LLMQuotaExceededError
from src.config.settings import Settings
from src.utils.helpers import hash_file, truncate_text
from src.utils.logger import get_logger, log_info, log_success, log_error, log_warning

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Resume profile schema (what Gemini should return)
# ---------------------------------------------------------------------------
RESUME_PARSE_PROMPT = """You are an expert resume analyzer. Parse the following resume text and extract structured information.

Return a valid JSON object with EXACTLY this structure (no markdown, no code fences, just raw JSON):

{{
    "name": "Full name of the candidate",
    "email": "Email address if found, else empty string",
    "phone": "Phone number if found, else empty string",
    "current_title": "Current or most recent job title",
    "summary": "A 2-3 sentence professional summary",
    "total_experience_years": <number>,
    "skills": ["skill1", "skill2", ...],
    "technical_skills": ["tech_skill1", "tech_skill2", ...],
    "soft_skills": ["soft_skill1", "soft_skill2", ...],
    "job_titles_held": ["title1", "title2", ...],
    "education": [
        {{
            "degree": "Degree name",
            "institution": "Institution name",
            "year": "Graduation year or empty string"
        }}
    ],
    "work_experience": [
        {{
            "title": "Job title",
            "company": "Company name",
            "duration": "Duration string (e.g., 'Jan 2020 - Present')",
            "highlights": ["Key achievement 1", "Key achievement 2"]
        }}
    ],
    "certifications": ["cert1", "cert2", ...],
    "languages": ["language1", "language2", ...],
    "key_achievements": ["achievement1", "achievement2", ...]
}}

IMPORTANT RULES:
1. Extract ALL skills mentioned, including programming languages, frameworks, tools, and platforms.
2. For total_experience_years, calculate from work history. If unclear, estimate conservatively.
3. Return ONLY the JSON object. No explanations, no markdown formatting.
4. If a field is not found in the resume, use an empty string or empty list as appropriate.

RESUME TEXT:
{resume_text}"""

# Minimum characters per page below which we treat the text layer as
# effectively empty and fall back to OCR (handles PDFs with a stray
# whitespace/control character but no real extractable text).
_MIN_CHARS_PER_PAGE = 10

# DPI used when rasterizing pages for OCR. Higher = more accurate but slower.
_OCR_RENDER_DPI = 300

# Common Tesseract install locations on Windows, checked if it's not on PATH.
# Covers both the official UB Mannheim installer's default paths.
_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _resolve_tesseract_cmd() -> str | None:
    """
    Locate the Tesseract OCR binary even if it's not on the system PATH.

    Checks, in order:
    1. The TESSERACT_CMD environment variable (explicit override).
    2. Whether `tesseract` is already resolvable on PATH.
    3. Common Windows install locations (since the Windows installer
       doesn't always add Tesseract to PATH, even when asked to).

    Returns:
        Path to the tesseract executable, or None if not found anywhere.
    """
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path and Path(env_path).exists():
        return env_path

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    for candidate in _WINDOWS_TESSERACT_PATHS:
        if Path(candidate).exists():
            return candidate

    return None


class ResumeParser(IResumeParser):
    """
    Parses PDF resumes into structured profiles using AI.

    Usage:
        parser = ResumeParser(llm_provider, repository, settings)
        profile = await parser.parse("path/to/resume.pdf")
    """

    def __init__(
        self, llm_provider: ILLMProvider, repository: IRepository, settings: Settings
    ) -> None:
        self._llm = llm_provider
        self._repo = repository
        self._settings = settings

    def _extract_pdf_text(self, pdf_path: str | Path) -> str:
        """
        Extract raw text from a PDF file using PyMuPDF, falling back to
        OCR if the PDF has no usable text layer (e.g. scanned resumes or
        image-only PDFs).

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Extracted text content.

        Raises:
            FileNotFoundError: If the PDF file doesn't exist.
            ValueError: If no text could be extracted, even via OCR.
        """
        import fitz  # PyMuPDF

        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")

        doc = fitz.open(str(path))
        try:
            text_parts = [page.get_text("text") for page in doc]
            full_text = "\n".join(text_parts).strip()

            avg_chars_per_page = len(full_text) / max(doc.page_count, 1)
            if full_text and avg_chars_per_page >= _MIN_CHARS_PER_PAGE:
                logger.debug(f"Extracted {len(full_text)} characters from {path.name}")
                return full_text

            # No usable text layer — likely a scanned/image-based PDF.
            log_warning(
                f"No text layer found in {path.name}, falling back to OCR "
                "(this may take a little longer)..."
            )
            return self._extract_pdf_text_via_ocr(doc, path)
        finally:
            doc.close()

    def _extract_pdf_text_via_ocr(self, doc, path: Path) -> str:
        """
        OCR fallback for PDFs with no extractable text layer.

        Rasterizes each page with PyMuPDF and runs Tesseract OCR on the
        resulting image. Requires the `pytesseract` Python package and the
        `tesseract-ocr` system binary to be installed.

        Args:
            doc: An already-open fitz.Document.
            path: Original PDF path (used for error messages/logging only).

        Returns:
            OCR-extracted text content.

        Raises:
            ValueError: If OCR also fails to extract any text, or if the
                required OCR dependencies are missing.
        """
        try:
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise ValueError(
                f"No text could be extracted from: {path}. The PDF appears to be "
                "scanned/image-based and OCR dependencies are missing. Install "
                "them with: pip install pytesseract pillow --break-system-packages "
                "(and ensure the 'tesseract-ocr' system package is installed)."
            ) from e

        tesseract_cmd = _resolve_tesseract_cmd()
        if not tesseract_cmd:
            raise ValueError(
                f"No text could be extracted from: {path}. The PDF appears to be "
                "scanned/image-based, but the Tesseract OCR engine binary could not "
                "be found on this machine (the `pytesseract` Python package alone "
                "isn't enough — it needs the actual OCR program installed separately).\n\n"
                "To fix this:\n"
                "  Windows: download and run the installer from "
                "https://github.com/UB-Mannheim/tesseract/wiki, then either let it "
                "add itself to PATH, or set an environment variable:\n"
                '      setx TESSERACT_CMD "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"\n'
                "  Linux/CI: sudo apt-get update && sudo apt-get install -y tesseract-ocr\n"
                "  macOS: brew install tesseract"
            )

        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        logger.debug(f"Using Tesseract OCR binary at: {tesseract_cmd}")

        zoom = _OCR_RENDER_DPI / 72  # fitz default is 72 DPI
        matrix = fitz.Matrix(zoom, zoom)

        ocr_text_parts = []
        for page_num, page in enumerate(doc):
            try:
                pixmap = page.get_pixmap(matrix=matrix)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                page_text = pytesseract.image_to_string(image)
                if page_text:
                    ocr_text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"OCR failed on page {page_num + 1} of {path.name}: {e}")

        ocr_full_text = "\n".join(ocr_text_parts).strip()

        if not ocr_full_text:
            raise ValueError(
                f"No text could be extracted from: {path} (no text layer, "
                "and OCR also returned no text — check that the scan is "
                "legible and tesseract-ocr is installed correctly)."
            )

        logger.debug(f"Extracted {len(ocr_full_text)} characters via OCR from {path.name}")
        return ocr_full_text

    async def parse(self, pdf_path: str | Path) -> dict:
        """
        Parse a resume PDF into a structured profile.

        Checks the local resume_profile.json first. If it exists, returns it.
        Otherwise checks the database cache. If cached, returns it and saves it locally.
        Otherwise, extracts text, sends to Gemini, and caches/saves the result.

        Args:
            pdf_path: Path to the PDF resume file.

        Returns:
            Dict with structured resume profile.
        """
        path = Path(pdf_path)

        # 1. Check if a local plaintext resume_profile.json exists
        profile_json_path = self._settings.project_root / "resume_profile.json"
        if isinstance(profile_json_path, Path) and profile_json_path.exists():
            try:
                profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
                log_info(f"Using local resume profile from {profile_json_path.name}")
                return profile
            except Exception as e:
                log_warning(
                    f"Failed to read local {profile_json_path.name}: {e}. Falling back to default parsing."
                )

        file_hash = hash_file(path)

        # Check database cache
        if self._repo:
            cached = await self._repo.get_cached_profile(file_hash)
            if cached:
                log_info(f"Using cached resume profile for {path.name}")
                # Save to local resume_profile.json for synchronization and editability
                try:
                    profile_json_path.write_text(
                        json.dumps(cached, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    log_info(f"Saved database cached profile to local {profile_json_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to write local resume_profile.json: {e}")
                return cached

        log_info(f"Parsing resume: {path.name}")

        # Extract text
        resume_text = self._extract_pdf_text(path)
        truncated_text = truncate_text(resume_text, max_length=15000)

        # Call Gemini
        prompt = RESUME_PARSE_PROMPT.format(resume_text=truncated_text)

        try:
            response_text = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.1,
                max_output_tokens=8192,
                response_mime_type="application/json",
            )

            profile = json.loads(response_text)
            log_success(f"Resume parsed successfully: {profile.get('name', 'Unknown')}")
            logger.info(
                f"Found {len(profile.get('skills', []))} skills, "
                f"{profile.get('total_experience_years', '?')} years experience"
            )

            # Write to local resume_profile.json
            try:
                profile_json_path.write_text(
                    json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                log_info(f"Saved parsed profile to local {profile_json_path.name}")
            except Exception as e:
                logger.warning(f"Failed to write local resume_profile.json: {e}")

            # Cache the result
            if self._repo:
                await self._repo.save_resume_profile(
                    file_hash=file_hash,
                    file_path=str(path),
                    parsed_json=json.dumps(profile, ensure_ascii=False),
                )

            return profile

        except LLMQuotaExceededError as e:
            if e.is_daily_quota:
                log_error(f"⚠️  Gemini daily quota exhausted: {e}")
            else:
                log_error(f"⚠️  Gemini rate limit hit: {e}")
            return {}
        except LLMAPIError as e:
            logger.error(str(e))
            return {}
        except Exception as e:
            log_error(f"Failed to parse resume with AI: {e}")
            return {}
