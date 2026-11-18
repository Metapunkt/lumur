"""Structured-light room scan: triangulation, planes, and room packages."""

from __future__ import annotations

from lumur.scan.pipeline import ScanResult, scan_from_correspondence
from lumur.scan.report import ScanReport, summarize_scan

__all__ = [
    "ScanResult",
    "ScanReport",
    "scan_from_correspondence",
    "summarize_scan",
]
