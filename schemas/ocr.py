"""请求/响应 Pydantic 模型"""

from typing import List

from pydantic import BaseModel, Field


# ─── 统一 OCR 响应 ───

class OCRLine(BaseModel):
    """单行 OCR 文字"""
    text: str = Field(..., description="识别文字")
    score: float = Field(..., description="识别置信度")
    bbox: List[int] = Field(..., description="文本框坐标 [x1,y1,x2,y2]")


class OCRBlock(BaseModel):
    """一个版面区域内的 OCR 结果"""
    label: str = Field(..., description="版面标签: doc_title, text, table, image, ...")
    label_name: str = Field(..., description="版面标签中文名: 文档标题、正文、表格、图片等")
    bbox: List[int] = Field(..., description="版面区域坐标 [x1,y1,x2,y2]")
    content: str = Field(default="", description="区域内所有文字，以 \\n 分行")
    confidence: float = Field(..., description="版面检测置信度")
    lines: List[OCRLine] = Field(default_factory=list, description="区域内每行 OCR 文字")


class OCRFileResult(BaseModel):
    """单张图片的 OCR 结果"""
    blocks: List[OCRBlock] = Field(default_factory=list, description="按版面区域分组的识别结果")
    version: str = Field(..., description="OCR 产线版本")
    backend: str = Field(..., description="推理后端")
    elapsed: float = Field(..., description="处理耗时（秒）")
    file_url: str = Field(default="", description="文件 URL（/url 接口）或空（/files 接口）")
    file_type: str = Field(default="", description="图片 MIME 类型")


class OCRResponse(BaseModel):
    """统一 OCR 响应"""
    results: List[OCRFileResult]


# ─── /api/ppocr/url 请求 ───

class OCRUrlRequest(BaseModel):
    """通过 URL 提交图片的 OCR 请求"""
    images: List[str] = Field(
        ..., min_length=1, max_length=20,
        description="图片 URL 列表（1-20 张）",
    )
    version: str = Field(
        ..., pattern="^(v5|v6)$", description="OCR 产线版本: v5 | v6",
    )
    backend: str = Field(
        ..., pattern="^(om|cpu)$", description="推理后端: om(NPU) | cpu",
    )
