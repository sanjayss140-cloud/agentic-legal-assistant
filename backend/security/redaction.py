import re
from typing import Tuple, Dict

# Regex patterns for personal identifiers
# Indian phone numbers with optional +91 or 0 prefix, or standard 10 digit
PHONE_PATTERN = re.compile(r'(?:\+?91[\-\s]?|0)?[6-9]\d{4}[\-\s]?\d{5}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b')
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
AADHAAR_PATTERN = re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b|\b[2-9]\d{3}[-\s]?\d{4}[-\s]?\d{4}\b')
PAN_PATTERN = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')

def mask_personal_identifiers(text: str, mask_parties: bool = False, party_names: list = None) -> Tuple[str, Dict[str, str]]:
    """
    Best-effort privacy masking before sending excerpts to external LLM providers.
    Replaces sensitive identifiers with opaque tokens [MASK_TOKEN_N] and records mapping.
    """
    if not text:
        return "", {}

    token_map = {}
    masked = text

    # 1. Emails
    email_count = 1
    for match in EMAIL_PATTERN.finditer(text):
        val = match.group(0)
        if val not in token_map.values():
            token = f"[EMAIL_{email_count}]"
            token_map[token] = val
            email_count += 1
    for token, val in token_map.items():
        if token.startswith("[EMAIL"):
            masked = masked.replace(val, token)

    # 2. PAN Numbers (5 letters, 4 numbers, 1 letter)
    pan_count = 1
    for match in PAN_PATTERN.finditer(masked):
        val = match.group(0)
        if val not in token_map.values():
            token = f"[PAN_{pan_count}]"
            token_map[token] = val
            pan_count += 1
    for token, val in token_map.items():
        if token.startswith("[PAN"):
            masked = masked.replace(val, token)

    # 3. Phone numbers (Match before Aadhaar to prioritize +91 mobile numbers)
    phone_count = 1
    for match in PHONE_PATTERN.finditer(masked):
        val = match.group(0)
        if val not in token_map.values():
            token = f"[PHONE_{phone_count}]"
            token_map[token] = val
            phone_count += 1
    for token, val in token_map.items():
        if token.startswith("[PHONE"):
            masked = masked.replace(val, token)

    # 4. Aadhaar Numbers (12-digit identity, 4-4-4 formatted)
    aadhaar_count = 1
    for match in AADHAAR_PATTERN.finditer(masked):
        val = match.group(0)
        if val not in token_map.values():
            token = f"[AADHAAR_{aadhaar_count}]"
            token_map[token] = val
            aadhaar_count += 1
    for token, val in token_map.items():
        if token.startswith("[AADHAAR"):
            masked = masked.replace(val, token)

    # 5. Optional party names
    if mask_parties and party_names:
        for idx, p in enumerate(party_names, start=1):
            if p and len(p.strip()) > 3 and p.strip() in masked:
                token = f"[PARTY_{idx}]"
                token_map[token] = p.strip()
                masked = masked.replace(p.strip(), token)

    return masked, token_map

def restore_personal_identifiers(masked_text: str, token_map: Dict[str, str]) -> str:
    """Restores masked tokens back to their original text for local display."""
    if not masked_text or not token_map:
        return masked_text
    
    restored = masked_text
    for token, original in token_map.items():
        restored = restored.replace(token, original)
    return restored
