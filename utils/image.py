"""图片解码工具"""

import asyncio
import io
import mimetypes
import urllib.request
from typing import List, Tuple

import numpy as np
from PIL import Image
from fastapi import UploadFile


async def read_uploaded_images(files: List[UploadFile]) -> List[np.ndarray]:
    """将上传文件列表解码为 numpy 数组列表"""
    result = []
    for f in files:
        data = await f.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        result.append(np.array(img))
    return result


async def download_image_from_url(url: str) -> Tuple[np.ndarray, str]:
    """从 URL 下载图片，返回 (numpy 数组, MIME 类型)

    使用 urllib（标准库）+ 线程池避免阻塞事件循环。
    """

    loop = asyncio.get_event_loop()

    def _fetch() -> Tuple[np.ndarray, str]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PP-OCR-Service/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return np.array(img), content_type

    arr, content_type = await loop.run_in_executor(None, _fetch)

    # 如果响应中没有 Content-Type，从 URL 后缀推断
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(url)
        content_type = guessed or "image/png"

    return arr, content_type
