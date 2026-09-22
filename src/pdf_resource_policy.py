"""Named PDF resource limits for the free-server deployment."""

MEBIBYTE = 1024 * 1024

# Manual uploads are held by Streamlit before application code runs, so keep
# this boundary lower than the official on-demand workflow.
MANUAL_PDF_MAX_BYTES = 32 * MEBIBYTE

# Official reports are downloaded only after a user action and are validated
# by the CNINFO downloader before parsing.
GENERAL_OFFICIAL_PDF_MAX_BYTES = 45 * MEBIBYTE
ONBOARDING_PDF_MAX_BYTES = 32 * MEBIBYTE
SNAPSHOT_PDF_MAX_BYTES = 45 * MEBIBYTE

# These are integrity boundaries, not truncation targets.  A document that
# exceeds either limit is rejected in full so the application never presents
# an incomplete extraction as complete evidence.
PDF_MAX_PAGES = 1000
# Eight million extracted characters is already far beyond the text volume of
# a normal A-share annual report.  Keeping the boundary below the old 20M
# value leaves enough headroom for PyMuPDF, Streamlit widgets and one
# request-local retrieval index on the 512MB free instance.
PDF_MAX_TEXT_CHARACTERS = 8_000_000
PDF_PARSE_WAIT_SECONDS = 0.25
