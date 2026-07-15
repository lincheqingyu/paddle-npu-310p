"""OCR 路由 — 版面分析优先的分区 OCR 流程。"""

import time
from typing import Annotated, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.requests import Request

from schemas.ocr import (
    OCRBlock,
    OCRFileResult,
    OCRLine,
    OCRResponse,
    OCRUrlRequest,
)
from services.pipeline_manager import PipelineNotReady, PipelineManager
from utils.image import download_image_from_url, read_uploaded_images

router = APIRouter(prefix="/api", tags=["ocr"])

LABEL_NAMES = {
    "abstract": "摘要",
    "algorithm": "算法",
    "aside_text": "旁注文本",
    "chart": "图表",
    "content": "内容",
    "display_formula": "行间公式",
    "doc_title": "文档标题",
    "figure_title": "图标题",
    "footer": "页脚",
    "footer_image": "页脚图片",
    "footnote": "脚注",
    "formula_number": "公式编号",
    "header": "页眉",
    "header_image": "页眉图片",
    "image": "图片",
    "inline_formula": "行内公式",
    "number": "编号",
    "paragraph_title": "段落标题",
    "reference": "参考文献标题",
    "reference_content": "参考文献内容",
    "seal": "印章",
    "table": "表格",
    "text": "正文",
    "vertical_text": "竖排文本",
    "vision_footnote": "视觉脚注",
}


def _get_manager(request: Request) -> PipelineManager:
    return request.app.state.manager


def _get_label_name(label: str) -> str:
    """Return the Chinese display name for a PP-DocLayoutV3 label."""
    return LABEL_NAMES.get(label, "未知版面类型")


def _normalize_bbox(box: List[int], image_width: int, image_height: int) -> List[int] | None:
    """Clamp a layout box to image bounds and discard empty regions."""
    if len(box) != 4:
        return None
    x1, y1, x2, y2 = (int(value) for value in box)
    x1 = max(0, min(x1, image_width))
    y1 = max(0, min(y1, image_height))
    x2 = max(0, min(x2, image_width))
    y2 = max(0, min(y2, image_height))
    return [x1, y1, x2, y2] if x2 > x1 and y2 > y1 else None


def _recognize_region(
    ocr_pipeline,
    image,
    bbox: List[int],
    label: str,
    confidence: float,
) -> OCRBlock:
    """Run OCR on one layout crop and convert line boxes to page coordinates."""
    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]
    lines: List[OCRLine] = []
    for result in ocr_pipeline.predict(crop):
        for text, score, box in zip(
            result["rec_texts"],
            result["rec_scores"],
            result.get("rec_boxes", []),
        ):
            bx1, by1, bx2, by2 = (int(value) for value in box)
            lines.append(
                OCRLine(
                    text=str(text),
                    score=round(float(score), 4),
                    bbox=[bx1 + x1, by1 + y1, bx2 + x1, by2 + y1],
                )
            )

    return OCRBlock(
        label=label,
        label_name=_get_label_name(label),
        bbox=bbox,
        content="\n".join(line.text for line in lines),
        confidence=round(confidence, 4),
        lines=lines,
    )


# ═══════════════════════════════════════════════════════════════
# 核心处理函数（两个端点共用）
# ═══════════════════════════════════════════════════════════════


def _process_image(
    ocr_pipeline,
    layout_pipeline,
    arr,
) -> List[OCRBlock]:
    """Run layout analysis first, then OCR each detected layout region."""
    image_height, image_width = arr.shape[:2]

    # 1. Layout analysis. Failure or no regions falls back to whole-image OCR.
    layout_boxes: List[dict] = []
    if layout_pipeline is not None:
        try:
            layout_output = list(layout_pipeline.predict(arr))
            if layout_output:
                layout_boxes = layout_output[0].get("boxes", [])
        except Exception:
            layout_boxes = []

    if not layout_boxes:
        return [
            _recognize_region(
                ocr_pipeline,
                arr,
                [0, 0, image_width, image_height],
                "text",
                0.0,
            )
        ]

    # 2. Each layout region is the ownership boundary for its OCR result.
    blocks: List[OCRBlock] = []
    for layout in layout_boxes:
        bbox = _normalize_bbox(
            layout.get("coordinate", []), image_width, image_height
        )
        if bbox is None:
            continue
        blocks.append(
            _recognize_region(
                ocr_pipeline,
                arr,
                bbox,
                str(layout.get("label", "unknown")),
                float(layout.get("score", 0.0)),
            )
        )

    # 3. Page reading order: top-to-bottom, then left-to-right.
    blocks.sort(key=lambda block: (block.bbox[1], block.bbox[0]))
    return blocks


def _raise_inference_unavailable(exc: Exception) -> None:
    """Convert backend failures into a stable API error response."""
    raise HTTPException(
        status_code=503,
        detail={
            "error": "OCR_INFERENCE_UNAVAILABLE",
            "message": "The selected OCR pipeline could not process the image.",
        },
    ) from exc


# ═══════════════════════════════════════════════════════════════
# POST /api/ppocr/files  — 文件上传
# ═══════════════════════════════════════════════════════════════


@router.post("/ppocr/files", response_model=OCRResponse)
async def ocr_predict_files(
    request: Request,
    files: Annotated[List[UploadFile], File(description="图片文件")],
    version: Annotated[str, Form(pattern="^(v5|v6)$", description="v5 | v6")],
    backend: Annotated[str, Form(pattern="^(om|cpu)$", description="om | cpu")],
):
    """上传图片文件进行 OCR 识别（含版面分析）"""
    manager = _get_manager(request)

    # 获取 pipeline
    try:
        ocr_pipeline = manager.get(version, backend)
    except PipelineNotReady as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "PIPELINE_NOT_READY", "available": e.available},
        )
    layout_pipeline = manager.get_layout()

    # 解码图片
    try:
        arrays = await read_uploaded_images(files)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # 逐张处理
    all_results: List[OCRFileResult] = []
    for upload, arr in zip(files, arrays):
        img_t0 = time.time()
        try:
            blocks = _process_image(ocr_pipeline, layout_pipeline, arr)
        except Exception as exc:
            _raise_inference_unavailable(exc)
        all_results.append(
            OCRFileResult(
                blocks=blocks,
                version=version,
                backend=backend,
                elapsed=round(time.time() - img_t0, 3),
                file_type=upload.content_type or "application/octet-stream",
            )
        )

    return OCRResponse(results=all_results)


# ═══════════════════════════════════════════════════════════════
# POST /api/ppocr/url  — URL 图片
# ═══════════════════════════════════════════════════════════════


@router.post("/ppocr/url", response_model=OCRResponse)
async def ocr_predict_url(
    request: Request,
    body: OCRUrlRequest,
):
    """通过图片 URL 进行 OCR 识别（含版面分析）"""
    manager = _get_manager(request)

    # 获取 pipeline
    try:
        ocr_pipeline = manager.get(body.version, body.backend)
    except PipelineNotReady as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "PIPELINE_NOT_READY", "available": e.available},
        )
    layout_pipeline = manager.get_layout()

    all_results: List[OCRFileResult] = []

    for url in body.images:
        t0 = time.time()

        # 下载图片
        try:
            arr, content_type = await download_image_from_url(url)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download image: {url} — {e}",
            )

        # 统一处理
        try:
            blocks = _process_image(ocr_pipeline, layout_pipeline, arr)
        except Exception as exc:
            _raise_inference_unavailable(exc)

        all_results.append(
            OCRFileResult(
                blocks=blocks,
                version=body.version,
                backend=body.backend,
                elapsed=round(time.time() - t0, 3),
                file_url=url,
                file_type=content_type,
            )
        )

    return OCRResponse(results=all_results)
