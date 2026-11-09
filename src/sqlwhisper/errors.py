class SourceError(Exception):
    """Bad upload, bad URL, unknown source or unreachable DB. Maps to HTTP 400."""
