"""LangChain adapter: thin loader that wraps the project's OCR + PDF extractor.

This module provides a small adapter that converts the output of
`extract_pages_pymupdf` into `langchain_core.documents.Document` objects while
preserving essential metadata and avoiding storing full OCR/native texts in
metadata (only lengths and short previews are kept).

Design goals:
- Keep the ingestion/OCR logic centralized in `rag_benchmark.py`.
- Provide safe fallbacks when LangChain is not installed.
- Add deterministic document IDs, full `source_path`, `ocr_strategy`, and
  simple `lineage` information for later chunking.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    # Prefer the lightweight `langchain_core` Document type for typing only.
    try:  # pragma: no cover - typing-time import
        from langchain_core.documents import Document as LC_Document
    except Exception:  # pragma: no cover - fallback typing
        LC_Document = Any


def _truncate_preview(text: str, max_len: int = 200) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def load_documents_from_pdf(
    pdf_path: Path, ocr_debug_dir: Optional[Path] = None, save_images: bool = True
) -> List[Union["LC_Document", Dict[str, Any]]]:
    """Load a PDF using the project's extractor and return LangChain Documents.

    - Returns a list of `langchain_core.documents.Document` when `langchain_core`
      is installed.
    - When LangChain is unavailable, returns simple dicts with `page_content`
      and `metadata` keys so the rest of the codebase can still operate.

    The returned metadata intentionally does NOT include the full `native_text`
    or `ocr_text` fields; instead it includes lengths and short previews.
    """
    import importlib
    import inspect

    # Deferred import of the project's extractor to avoid circular imports.
    from rag_benchmark import extract_pages_pymupdf  # type: ignore

    # Try to import the LangChain core Document class at runtime.
    Document = None
    try:
        lc_docs = importlib.import_module("langchain_core.documents")
        Document = getattr(lc_docs, "Document")
    except Exception:
        Document = None

    pdf_path = Path(pdf_path)
    debug_dir = Path(ocr_debug_dir) if ocr_debug_dir is not None else Path("ocr_debug")
    pages = extract_pages_pymupdf(pdf_path, debug_dir=debug_dir, ocr_debug=True, save_images=save_images)

    docs: List[Union["LC_Document", Dict[str, Any]]] = []
    for page in pages:
        page_num = int(page.get("page", 0))

        native_text = (page.get("native_text") or "")
        ocr_text = (page.get("ocr_text") or "")
        selected_text = (page.get("text") or "")

        # Determine a simple OCR strategy tag.
        if bool(page.get("ocr_used")):
            if not native_text.strip():
                ocr_strategy = "ocr_only"
            elif not ocr_text.strip():
                ocr_strategy = "native"
            else:
                ocr_strategy = "merged"
        else:
            ocr_strategy = "native"

        # Deterministic document id using absolute path + page number.
        doc_id = f"{str(pdf_path.resolve())}::page_{page_num:03d}"

        metadata: Dict[str, Any] = {
            "document_id": doc_id,
            "page": page_num,
            "lineage": {"page": page_num},
            "ocr_used": bool(page.get("ocr_used", False)),
            "ocr_quality": float(page.get("ocr_quality", 0.0)),
            "ocr_confidence": float(page.get("ocr_confidence", 0.0)),
            "ocr_strategy": ocr_strategy,
            "source_path": str(pdf_path.resolve()),
            # Keep only short previews and lengths to avoid storing full text in metadata
            "native_text_len": len(native_text or ""),
            "native_text_preview": _truncate_preview(native_text, max_len=200),
            "ocr_text_len": len(ocr_text or ""),
            "ocr_text_preview": _truncate_preview(ocr_text, max_len=200),
        }

        content = selected_text

        if Document is not None:
            # Some Document constructors support an `id` parameter; detect dynamically.
            try:
                sig = inspect.signature(Document)
                if "id" in sig.parameters:
                    docs.append(Document(page_content=content, metadata=metadata, id=doc_id))
                else:
                    docs.append(Document(page_content=content, metadata=metadata))
            except Exception:
                # Fallback when the constructor behaves unexpectedly.
                docs.append(Document(page_content=content, metadata=metadata))
        else:
            docs.append({"page_content": content, "metadata": metadata})

    return docs
