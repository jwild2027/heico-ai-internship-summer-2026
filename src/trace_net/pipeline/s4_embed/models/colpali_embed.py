"""Render image/PDF page, process with ColPali processor, and optionally produce embeddings.

Usage examples:
  python colpali_embed.py --image "C:\path\to\img.png" --model "path-or-model-id" --device cpu --output emb.npy
  python colpali_embed.py --pdf "C:\path\to\doc.pdf" --page 0 --poppler-path "C:\poppler\Library\bin" --output emb.npy

Notes:
 - If `--model` is not provided, the script will only run the processor and print tensor shapes.
 - Loading a pretrained model may download weights from Hugging Face and require ample RAM.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from PIL import Image
import numpy as np

try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

import torch

try:
    from colpali_engine.models import ColPali
    from colpali_engine.models.paligemma.colpali.processing_colpali import ColPaliProcessor
except Exception:
    # support package layout used in some installs
    try:
        from colpali_engine.models.paligemma.colpali.processing_colpali import ColPaliProcessor
        from colpali_engine.models import ColPali
    except Exception as e:
        ColPali = None
        ColPaliProcessor = None
        _import_err = e


def render_pdf_page(pdf_path: str, page: int = 0, dpi: int = 300, poppler_path: Optional[str] = None):
    if convert_from_path is None:
        raise RuntimeError("pdf2image not available; install pdf2image and poppler")
    images = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_path)
    if not images:
        raise RuntimeError(f"No images rendered from {pdf_path}")
    if page < 0 or page >= len(images):
        raise IndexError("page index out of range")
    return images[page]


def load_image(path: str) -> Image.Image:
    return Image.open(path)


def process_images_with_processor(processor, images):
    batch = processor.process_images(images)
    return batch


def model_forward_and_pool(model, processor, batch, device: str = "cpu"):
    # Move tensors to device
    device_t = torch.device(device)
    batch = {k: (v.to(device_t) if isinstance(v, torch.Tensor) else v) for k, v in batch.items()}

    with torch.no_grad():
        proj = model(**batch)  # expected shape (batch, seq_len, dim)

    # identify image token positions
    input_ids = batch.get("input_ids")
    if input_ids is None:
        raise RuntimeError("processor output missing input_ids")

    image_token_index = processor.image_token_index
    image_mask = (input_ids == image_token_index).unsqueeze(-1).to(proj.dtype)  # (batch, seq_len, 1)

    summed = (proj * image_mask).sum(dim=1)  # (batch, dim)
    counts = image_mask.sum(dim=1).clamp(min=1e-6)
    embeds = summed / counts

    # L2 normalize
    embeds = embeds / embeds.norm(dim=-1, keepdim=True)

    return embeds.cpu().numpy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render and embed images with ColPali")
    parser.add_argument("--image", type=str, help="Path to image file")
    parser.add_argument("--pdf", type=str, help="Path to PDF file")
    parser.add_argument("--page", type=int, default=0, help="Page index for PDF (0-based)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for PDF rendering")
    parser.add_argument("--poppler-path", type=str, help="Poppler bin folder path (for pdf2image)")
    parser.add_argument("--model", type=str, help="Pretrained model id or local path to ColPali (optional)")
    parser.add_argument("--device", type=str, default="cpu", help="Torch device (cpu/cuda)")
    parser.add_argument("--output", type=str, help="Output .npy file for embeddings")
    args = parser.parse_args(argv)

    if (not args.image) and (not args.pdf):
        parser.error("Either --image or --pdf must be provided")

    # load image
    if args.pdf:
        img = render_pdf_page(args.pdf, page=args.page, dpi=args.dpi, poppler_path=args.poppler_path)
    else:
        img = load_image(args.image)

    # ensure processor is available
    if ColPaliProcessor is None:
        print("ColPaliProcessor not importable. Ensure colpali packages are installed.")
        raise _import_err

    # load processor
    if args.model:
        print(f"Loading processor from: {args.model}")
        processor = ColPaliProcessor.from_pretrained(args.model)
    else:
        print("Loading default ColPaliProcessor (no model) - this may still attempt to download processor files if not cached.")
        # attempt to create a processor with default configs
        processor = ColPaliProcessor()

    batch = process_images_with_processor(processor, [img])
    print("Processed batch keys:", list(batch.keys()))
    for k, v in batch.items():
        if hasattr(v, "shape"):
            try:
                print(f"  {k}: {v.shape}")
            except Exception:
                print(f"  {k}: (type={type(v)})")

    if args.model:
        if ColPali is None:
            print("ColPali model class not importable. Ensure colpali packages are installed.")
            raise _import_err
        print(f"Loading ColPali model from: {args.model}")
        model = ColPali.from_pretrained(args.model)
        model = model.eval()
        model_device = args.device
        if model_device != "cpu":
            model = model.to(model_device)

        embeds = model_forward_and_pool(model, processor, batch, device=args.device)
        print("Embeddings shape:", embeds.shape)
        if args.output:
            np.save(args.output, embeds)
            print(f"Saved embeddings to {args.output}")
    else:
        print("No --model provided; skipping model forward. Use --model to load weights and compute embeddings.")


if __name__ == "__main__":
    main()
