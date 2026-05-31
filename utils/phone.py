def normalize_phone(phone: str) -> str:
    """Normalize to +7XXXXXXXXXX format."""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith(('7', '8')):
        return '+7' + digits[1:]
    if len(digits) == 10:
        return '+7' + digits
    if len(digits) == 12 and digits.startswith('7'):
        return '+' + digits
    return phone.strip()
