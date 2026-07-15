"""
应用配置，所有环境变量读取集中在一处。
优先级：系统环境变量 > .env 文件 > 默认值
容器化部署时通过 docker run -e 传入即可覆盖 .env 的值。
"""

import os

from dotenv import load_dotenv

load_dotenv()  # 有 .env 就读，没有跳过


class AppConfig:
    # ─── PP-OCRv5 OM (NPU) ───
    V5_DET_OM = os.getenv(
        "OCR_V5_DET_OM_DIR", "/models/om/PP-OCRv5_server_det"
    )
    V5_REC_OM = os.getenv(
        "OCR_V5_REC_OM_DIR", "/models/om/PP-OCRv5_server_rec"
    )

    # ─── PP-OCRv6 OM (NPU) ───
    V6_DET_OM = os.getenv(
        "OCR_V6_DET_OM_DIR", "/models/om/ppocrv6_medium_det"
    )
    V6_REC_OM = os.getenv(
        "OCR_V6_REC_OM_DIR", "/models/om/ppocrv6_medium_rec"
    )

    # ─── PP-OCRv5 CPU (ONNX Runtime) ───
    V5_DET_CPU = os.getenv(
        "OCR_V5_DET_ONNX_DIR", "/models/onnx/PP-OCRv5_server_det"
    )
    V5_REC_CPU = os.getenv(
        "OCR_V5_REC_ONNX_DIR", "/models/onnx/PP-OCRv5_server_rec"
    )

    # ─── PP-OCRv6 CPU (ONNX Runtime) ───
    V6_DET_CPU = os.getenv(
        "OCR_V6_DET_ONNX_DIR", "/models/onnx/ppocrv6_medium_det"
    )
    V6_REC_CPU = os.getenv(
        "OCR_V6_REC_ONNX_DIR", "/models/onnx/ppocrv6_medium_rec"
    )

    # ─── 版面检测 (PP-DocLayoutV3 OM/NPU) ───
    LAYOUT_DET_MODEL_DIR = os.getenv(
        "LAYOUT_DET_MODEL_DIR", "/models/om/PP-DocLayoutV3"
    )

    # ─── OCR 识别分数阈值 ───
    OCR_REC_SCORE_THRESHOLD = float(
        os.getenv("OCR_REC_SCORE_THRESHOLD", "0.8")
    )

    # ─── 服务 ───
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8080"))


# 全局单例，启动时导入一次即可
config = AppConfig()
