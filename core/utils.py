from datetime import datetime

def generate_case_number(complaints_id):
    """
    Generates a real, permanent case number at creation time, e.g. CMP-2026-0001.
    Uses the actual current year — call this once, when the Complaints row is first saved.
    """
    from datetime import datetime
    year = datetime.now().year
    return f"CMP-{year}-{str(complaints_id).zfill(4)}"

def generate_certificate_number(cfa_id):
    """Generates: CFA-2026-0001"""
    from datetime import datetime
    year = datetime.now().year
    return f"CFA-{year}-{str(cfa_id).zfill(4)}"

def generate_document_id(document_request_id):
    """Generates: DOC-2026-0001"""
    year = datetime.now().year
    return f'DOC-{year}-{str(document_request_id).zfill(4)}'

ALLOWED_MIME_TYPES      = {'image/jpeg', 'image/png', 'image/jpg'}
ALLOWED_EXTENSIONS      = {'jpg', 'jpeg', 'png'}   
MAX_UPLOAD_BYTES        = 5 * 1024 * 1024  # 5 MB

def validate_upload(file):
    """
    Returns (True, None) if valid.
    Returns (False, error_message) if invalid.
    """
    if file is None:
        return False, "No file was uploaded."

    # Extension check                                 
    ext = file.name.rsplit('.', 1)[-1].lower()        
    if ext not in ALLOWED_EXTENSIONS:                 
        return False, "Only JPG and PNG files are allowed."  

    if file.content_type not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type '{file.content_type}'. Only JPG and PNG are allowed."

    if file.size > MAX_UPLOAD_BYTES:
        size_mb = file.size / (1024 * 1024)
        return False, f"File too large ({size_mb:.1f} MB). Maximum is 5 MB."

    # Check file magic bytes (prevent extension spoofing)
    header = file.read(8)
    file.seek(0)
    jpeg_magic = (b'\xff\xd8\xff',)
    png_magic  = (b'\x89PNG',)
    if not (any(header.startswith(m) for m in jpeg_magic) or
            any(header.startswith(m) for m in png_magic)):
        return False, "File content does not match image format."

    return True, None