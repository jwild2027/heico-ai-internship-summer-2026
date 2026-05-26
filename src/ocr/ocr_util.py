"""OCR utility for extracting text from images and PDFs using Tesseract."""

from PIL import Image, ImageOps
import pytesseract
from pdf2image import convert_from_path
from typing import Optional

# Set Tesseract binary path for Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"


def ocr_image(img: Image.Image, lang: str = "eng", preprocess: bool = True) -> str:
    """
    Extract text from a PIL Image using Tesseract OCR.
    
    Args:
        img: PIL Image object
        lang: Tesseract language code (default: "eng")
        preprocess: If True, convert to grayscale for better OCR accuracy
    
    Returns:
        Extracted text string
    """
    if preprocess:
        img = ImageOps.grayscale(img)
    
    text = pytesseract.image_to_string(img, lang=lang)
    return text.strip()


def ocr_pdf(
    pdf_path: str,
    poppler_path: Optional[str] = None,
    dpi: int = 300,
    lang: str = "eng"
) -> str:
    """
    Extract text from a PDF file using Tesseract OCR.
    
    Args:
        pdf_path: Path to PDF file
        poppler_path: Optional path to Poppler bin folder (for pdf2image)
        dpi: DPI for PDF rendering (higher = better OCR, slower)
        lang: Tesseract language code (default: "eng")
    
    Returns:
        Extracted text string with page breaks
    """
    try:
        images = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_path)
        pages = [ocr_image(img, lang=lang, preprocess=True) for img in images]
        return "\n\n--- Page Break ---\n\n".join(pages)
    except Exception as e:
        print(f"Error during PDF OCR: {e}")
        raise


def ocr_pdf_hocr(
    pdf_path: str,
    poppler_path: Optional[str] = None,
    dpi: int = 300,
    lang: str = "eng"
) -> bytes:
    """
    Generate searchable PDF using hOCR output from Tesseract.
    
    Args:
        pdf_path: Path to input PDF file
        poppler_path: Optional path to Poppler bin folder
        dpi: DPI for PDF rendering
        lang: Tesseract language code
    
    Returns:
        Bytes of searchable PDF
    """
    images = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_path)
    if not images:
        raise ValueError(f"No images extracted from {pdf_path}")
    
    pdf_bytes = pytesseract.image_to_pdf_or_hocr(images[0], extension='pdf', lang=lang)
    return pdf_bytes


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="OCR utility for PDFs and images")
    parser.add_argument("--pdf", type=str, help="Path to PDF file to OCR")
    parser.add_argument("--image", type=str, help="Path to image file to OCR")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for PDF rendering (default: 300)")
    parser.add_argument("--lang", type=str, default="eng", help="Tesseract language code (default: eng)")
    parser.add_argument("--output", type=str, help="Optional output file to save extracted text")
    parser.add_argument("--poppler-path", type=str, help="Path to Poppler bin folder (e.g., C:\\poppler-24.08.0\\Library\\bin)")
    
    args = parser.parse_args()
    
    try:
        if args.pdf:
            print(f"📄 Processing PDF: {args.pdf}")
            text = ocr_pdf(args.pdf, poppler_path=args.poppler_path, dpi=args.dpi, lang=args.lang)
            print(f"\n✓ Extraction complete ({len(text)} characters)\n")
            print(text)
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"\n✓ Text saved to: {args.output}")
        
        elif args.image:
            print(f"🖼️  Processing image: {args.image}")
            img = Image.open(args.image)
            text = ocr_image(img, lang=args.lang)
            print(f"\n✓ Extraction complete ({len(text)} characters)\n")
            print(text)
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"\n✓ Text saved to: {args.output}")
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
