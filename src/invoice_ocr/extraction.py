"""Rule-based key-value extraction for invoices.

Deliberately uses regex + keyword heuristics instead of a heavy model: it is
fast, explainable, runs on any machine, and is easy to unit test. Every field
carries a flag so downstream code can see what was (not) found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ---- Patterns --------------------------------------------------------------

# Thousands groups of exactly 3 digits (separator may be ',', '.' or a space, since
# Tesseract frequently reads "3,549.00" as "3.549.00"), then optional 1-2 decimals.
_AMOUNT = r"([0-9]{1,3}(?:[,.\s][0-9]{3})+(?:[.,][0-9]{1,2})?|[0-9]+(?:[.,][0-9]{1,2})?)"
_CURRENCY = r"(?:Rs\.?|INR|USD|EUR|GBP|\$|€|£|₹)?\s*"

# The label tolerates common OCR slips ("tnvoice", "lnvoice", "1nvoice"), and the
# value tolerates a stray bracket/pipe where a leading "I" was misread.
INVOICE_NO_RE = re.compile(
    r"(?:[il1t]n?[vy]o[il1]ce|inv|bill)\s*(?:n[o0]\.?|number|num|#|id)?\s*[:#\-]?\s*"
    r"([\(\[\|!]?[A-Z0-9][A-Z0-9\-/]{2,})",
    re.IGNORECASE,
)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), ("%Y", "%m", "%d")),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), ("%d", "%m", "%Y")),
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"), ("%d", "%b", "%Y")),
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b"), ("%b", "%d", "%Y")),
]
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){9,11}\d(?!\d)")

TOTAL_KEYWORDS = [
    r"grand\s*total", r"total\s*amount(?:\s*due)?", r"amount\s*due", r"balance\s*due",
    r"net\s*payable", r"total\s*payable", r"total",
]
SUBTOTAL_RE = re.compile(r"sub\s*-?\s*total\s*[:\-]?\s*" + _CURRENCY + _AMOUNT, re.IGNORECASE)
TAX_RE = re.compile(
    r"(?:tax|gst|vat|igst|cgst|sgst)(?:\s*\(?\d{1,2}(?:\.\d+)?\s*%\)?)?\s*[:\-]?\s*" + _CURRENCY + _AMOUNT,
    re.IGNORECASE,
)
DATE_LABELS = {
    "invoice_date": re.compile(r"(?:invoice\s*date|date\s*of\s*issue|issued?|date)\b", re.I),
    "due_date": re.compile(r"(?:[d0oq]ue\s*date|payment\s*due|[d0oq]ue\s*on|[d0oq]ue)\b", re.I),
}
VENDOR_SKIP = re.compile(
    r"invoice|bill\s*to|ship\s*to|date|total|tax|gst|page|receipt|www\.|@|^\d", re.I
)


@dataclass
class InvoiceFields:
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None
    gstin: str | None = None
    email: str | None = None
    phone: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    arithmetic_ok: bool | None = None  # subtotal + tax == total (within tolerance)

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Helpers ---------------------------------------------------------------

def parse_amount(raw: str) -> float | None:
    """Parse "1,234.50", "1.234.50" (OCR comma->dot slip) or "1234" into a float.

    The last separator is the decimal point only when followed by 1-2 digits;
    every other separator is a thousands separator.
    """
    s = re.sub(r"\s", "", raw)
    m = re.match(r"^(.*?)[.,](\d{1,2})$", s)
    whole, frac = (re.sub(r"[.,]", "", m.group(1)), m.group(2)) if m else (re.sub(r"[.,]", "", s), "")
    try:
        return float(f"{whole}.{frac}" if frac else whole)
    except ValueError:
        return None


def normalise_date(day_month_year: tuple[str, str, str], fmts: tuple[str, str, str]) -> str | None:
    """Try to build an ISO date (YYYY-MM-DD) from the matched groups."""
    candidate = " ".join(day_month_year)
    fmt = " ".join(fmts)
    for variant in (fmt, fmt.replace("%b", "%B")):
        try:
            return datetime.strptime(candidate, variant).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _find_dates(line: str) -> list[str]:
    found: list[str] = []
    for pattern, fmts in DATE_PATTERNS:
        for m in pattern.finditer(line):
            iso = normalise_date(m.groups(), fmts)
            if iso:
                found.append(iso)
    return found


def _detect_currency(text: str) -> str | None:
    symbols = {"₹": "INR", "Rs": "INR", "INR": "INR", "$": "USD", "USD": "USD",
               "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}
    for symbol, code in symbols.items():
        if symbol in text:
            return code
    return None


# ---- Field extractors ------------------------------------------------------

def _extract_invoice_number(text: str) -> str | None:
    for line in text.splitlines():
        m = INVOICE_NO_RE.search(line)
        if m:
            raw = m.group(1)
            value = raw.lstrip("([|!").strip("-/")
            # Skip false positives like the word "INVOICE" followed by "DATE".
            if value.upper() in {"DATE", "TO", "FROM", "DETAILS"} or not re.search(r"\d", value):
                continue
            # Repair: a leading "I" misread as a bracket/pipe turns "INV-..." into "(NV-...".
            if raw[0] in "([|!" and value.upper().startswith("NV-"):
                value = "I" + value
            return value
    return None


def _extract_dates(text: str) -> tuple[str | None, str | None]:
    invoice_date = due_date = None
    all_dates: list[str] = []
    for line in text.splitlines():
        dates = _find_dates(line)
        if not dates:
            continue
        all_dates.extend(dates)
        if DATE_LABELS["due_date"].search(line) and due_date is None:
            due_date = dates[0]
        elif DATE_LABELS["invoice_date"].search(line) and invoice_date is None:
            invoice_date = dates[0]
    if invoice_date is None and all_dates:
        invoice_date = all_dates[0]
    return invoice_date, due_date


def _extract_total(text: str) -> float | None:
    lines = text.splitlines()
    for keyword in TOTAL_KEYWORDS:
        # "sub total" must not satisfy the plain "total" keyword.
        pattern = re.compile(
            r"(?<!sub)(?<!sub\s)(?<!sub-)" + keyword + r"\s*[:\-]?\s*" + _CURRENCY + _AMOUNT,
            re.IGNORECASE,
        )
        candidates = []
        for line in lines:
            m = pattern.search(line)
            if m:
                value = parse_amount(m.group(1))
                if value is not None:
                    candidates.append(value)
        if candidates:
            # The last matching line is usually the final payable amount.
            return candidates[-1]
    return None


_TITLE_WORDS = re.compile(r"\b(?:tax\s+)?invoice\b|\bbill\b|\breceipt\b", re.IGNORECASE)
_TABLE_HEADER = re.compile(r"description|qty|quantity|rate|amount|item|price", re.IGNORECASE)


def _extract_vendor(text: str) -> str | None:
    """Vendor is normally the first meaningful line; the page title (INVOICE) is stripped.

    OCR often joins the vendor and the title into one line ("Nova Tech INVOICE"),
    so we remove the title word instead of discarding the whole line.
    """
    for line in text.splitlines()[:8]:
        line = _TITLE_WORDS.sub("", line).strip(" :-|")
        if len(line) < 3 or _TABLE_HEADER.search(line):
            continue
        if re.search(r"bill\s*to|ship\s*to|date|total|gst|tax|page|www\.|@", line, re.I):
            continue
        if re.match(r"^\d", line):  # street addresses / numbers
            continue
        if sum(c.isalpha() for c in line) >= 3:
            return line
    return None


# ---- Public API ------------------------------------------------------------

def extract_invoice_fields(text: str) -> InvoiceFields:
    """Extract structured fields from OCR text."""
    fields = InvoiceFields()
    fields.vendor_name = _extract_vendor(text)
    fields.invoice_number = _extract_invoice_number(text)
    fields.invoice_date, fields.due_date = _extract_dates(text)
    fields.currency = _detect_currency(text)

    if m := SUBTOTAL_RE.search(text):
        fields.subtotal = parse_amount(m.group(1))
    if m := TAX_RE.search(text):
        fields.tax = parse_amount(m.group(1))
    fields.total = _extract_total(text)

    if m := GSTIN_RE.search(text):
        fields.gstin = m.group(1)
    if m := EMAIL_RE.search(text):
        fields.email = m.group(0)
    if m := PHONE_RE.search(text):
        fields.phone = re.sub(r"\s+", " ", m.group(0)).strip()

    # Business-rule validation: catches OCR digit errors that field presence alone would miss.
    if None not in (fields.subtotal, fields.tax, fields.total):
        fields.arithmetic_ok = abs(fields.subtotal + fields.tax - fields.total) <= 0.02

    required = ["vendor_name", "invoice_number", "invoice_date", "total"]
    fields.missing_fields = [name for name in required if getattr(fields, name) is None]
    return fields
