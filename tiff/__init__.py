"""TIFF ingestion helpers for the local HEICO RAG prototype.

This package is intentionally separate from the existing PDF pipeline so TIFF
inventory and metadata extraction can be added without breaking the current
PDF/Chroma/Ollama workflow.
"""

from .inventory import TIFFInventoryRecord, build_tiff_inventory_record, inventory_directory
from .metadata_parser import ParsedDrawingMetadata, parse_title_block_text

__all__ = [
    "TIFFInventoryRecord",
    "build_tiff_inventory_record",
    "inventory_directory",
    "ParsedDrawingMetadata",
    "parse_title_block_text",
]
