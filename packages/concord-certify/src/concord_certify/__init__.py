"""concord-certify: integration certification toolkit for Concord source plugins.

Runs a plugin exactly as Concord runs it (the adapter SDK's out-of-process plugin host),
measures what it delivers and writes a JSON + Markdown report with an explicit validation
level. Software checks only: a pass is never hardware certification and never human
validation (see docs/CERTIFICATION.md).
"""

__version__ = "0.1.0"
REPORT_VERSION = "1.0"

__all__ = ["REPORT_VERSION", "__version__"]
