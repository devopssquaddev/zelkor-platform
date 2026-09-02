"""Configure Zelkor logging before `aegra db upgrade`."""
from zelkor_logging import configure_logging

configure_logging("zelkor-aegra-cli")
