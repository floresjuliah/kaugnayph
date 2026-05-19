from datetime import datetime
 
def generate_case_id(complaints_id):
    """Generates: CMP-2026-0001"""
    year = datetime.now().year
    return f'CMP-{year}-{str(complaints_id).zfill(4)}'
 
def generate_document_id(document_request_id):
    """Generates: DOC-2026-0001"""
    year = datetime.now().year
    return f'DOC-{year}-{str(document_request_id).zfill(4)}'