"""The vision reader: scanned pages are transcribed (C25), chart pages described in max 300 tokens (C27).
Uses the largest image embedded in the page (a scan is usually one full-page image)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from app import llm, prompts
from app.core import config
from app.files.common import CHART_OUT_TOKENS, IMAGE_EXT, SCAN_OUT_TOKENS


def page_image(data: bytes, name: str, page_no: int) -> tuple[bytes, str] | None:
    """(image bytes, format) of the page, or None (vector chart, or no image)."""
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        return data, {"jpg": "jpeg"}.get(ext[1:], ext[1:])
    if ext != ".pdf":
        from app.files.readers import embedded_images
        images = embedded_images(name, data, page_no)
        if not images:
            return None
        from PIL import Image
        decoded = [Image.open(io.BytesIO(image)).convert("RGB") for image in images]
        width = min(2400, max(i.width for i in decoded))
        fitted = []
        for im in decoded:
            im.thumbnail((width, 2400))
            fitted.append(im)
        composite = Image.new("RGB", (width, sum(i.height for i in fitted)), "white")
        top = 0
        for im in fitted:
            composite.paste(im, (0, top)); top += im.height
        result = io.BytesIO()
        composite.save(result, "PNG")
        return result.getvalue(), "png"
    try:
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(data) as document:
            page = document[page_no - 1]
            image = page.render(scale=1.5).to_pil()
            output = io.BytesIO()
            image.save(output, "PNG")
            return output.getvalue(), "png"
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        page = PdfReader(io.BytesIO(data)).pages[page_no - 1]
        best = max(page.images, key=lambda img: len(img.data), default=None)
        if best is None:
            return None
        e = Path(best.name).suffix.lower().lstrip(".") or "png"
        return best.data, {"jpg": "jpeg"}.get(e, e)
    except Exception:
        return None


async def read_page(img: bytes, fmt: str, kind: str, ctx: llm.CallContext) -> str:
    prompt = prompts.render("files/ocr_scan" if kind == "scan" else "files/chart")
    url = f"data:image/{fmt};base64,{base64.b64encode(img).decode()}"
    res = await llm.complete(config.VISION_MODEL, [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
                             stage="file:ocr" if kind == "scan" else "file:chart", ctx=ctx, temperature=0.0,
                             max_tokens=SCAN_OUT_TOKENS if kind == "scan" else CHART_OUT_TOKENS, need_vision=True,
                             max_retries=0, allow_fallback=False)
    return res.text.strip()
