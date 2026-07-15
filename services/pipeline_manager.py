"""
Pipeline 管理器：模型预加载 + 运行时获取。
所有 YAML 模板内嵌为 Python dict，不依赖外部配置文件。
"""

import copy
import hashlib
import time
from pathlib import Path
from typing import Optional

from paddlex import create_pipeline
from paddlex.inference.pipelines import BasePipeline

from config import config

# ═══════════════════════════════════════════
# YAML 模板 (dict)
# ═══════════════════════════════════════════

OM_TEMPLATE = {
    "pipeline_name": "OCR",
    "text_type": "general",
    "use_doc_preprocessor": False,
    "use_textline_orientation": False,
    "hpi_config": {"auto_config": False, "backend": "om"},
    "SubModules": {
        "TextDetection": {
            "module_name": "text_detection",
            "model_name": None,      # ← 运行时注入
            "model_dir": None,       # ← 运行时注入
            "limit_side_len": 960,
            "limit_type": "max",
            "max_side_limit": 4000,
            "thresh": 0.3,
            "box_thresh": 0.6,
            "unclip_ratio": 1.5,
            "input_shape": [3, 960, 960],
        },
        "TextLineOrientation": {
            "module_name": "textline_orientation",
            "model_name": "PP-LCNet_x0_25_textline_ori",
            "model_dir": None,
            "batch_size": 6,
        },
        "TextRecognition": {
            "module_name": "text_recognition",
            "model_name": None,      # ← 运行时注入
            "model_dir": None,       # ← 运行时注入
            "batch_size": 1,
            "score_thresh": 0.0,
            "input_shape": [3, 48, 320],
        },
    },
}

CPU_TEMPLATE = {
    "pipeline_name": "OCR",
    "text_type": "general",
    "use_doc_preprocessor": False,
    "use_textline_orientation": False,
    "hpi_config": {"auto_config": False, "backend": "onnxruntime"},
    "SubModules": {
        "TextDetection": {
            "module_name": "text_detection",
            "model_name": None,
            "model_dir": None,
            "limit_side_len": 960,
            "limit_type": "max",
            "max_side_limit": 4000,
            "thresh": 0.3,
            "box_thresh": 0.6,
            "unclip_ratio": 1.5,
        },
        "TextLineOrientation": {
            "module_name": "textline_orientation",
            "model_name": "PP-LCNet_x0_25_textline_ori",
            "model_dir": None,
            "batch_size": 6,
        },
        "TextRecognition": {
            "module_name": "text_recognition",
            "model_name": None,
            "model_dir": None,
            "batch_size": 1,
            "score_thresh": 0.0,
        },
    },
}

# ═══════════════════════════════════════════
# 版面检测模板 (PP-DocLayoutV3)
# ═══════════════════════════════════════════

LAYOUT_DET_TEMPLATE = {
    "pipeline_name": "object_detection",
    "hpi_config": {"auto_config": False, "backend": "om"},
    "SubModules": {
        "ObjectDetection": {
            "module_name": "object_detection",
            "model_name": None,      # ← 运行时注入
            "model_dir": None,       # ← 运行时注入
        }
    },
}

# ═══════════════════════════════════════════
# Pipeline 注册表: key → (模板, 设备, det目录, rec目录, det名, rec名)
# ═══════════════════════════════════════════

PIPELINE_DEFS = [
    # ─── v5 OM (NPU) ───
    (
        "v5:om", OM_TEMPLATE, "npu:0",
        config.V5_DET_OM, config.V5_REC_OM,
        "PP-OCRv5_server_det", "PP-OCRv5_server_rec",
    ),
    # ─── v5 CPU ───
    (
        "v5:cpu", CPU_TEMPLATE, "cpu",
        config.V5_DET_CPU, config.V5_REC_CPU,
        "PP-OCRv5_server_det", "PP-OCRv5_server_rec",
    ),
    # ─── v6 OM (NPU) ───
    (
        "v6:om", OM_TEMPLATE, "npu:0",
        config.V6_DET_OM, config.V6_REC_OM,
        "PP-OCRv6_medium_det", "PP-OCRv6_medium_rec",
    ),
    # ─── v6 CPU ───
    (
        "v6:cpu", CPU_TEMPLATE, "cpu",
        config.V6_DET_CPU, config.V6_REC_CPU,
        "PP-OCRv6_medium_det", "PP-OCRv6_medium_rec",
    ),
]

# ═══════════════════════════════════════════
# 版面检测 Pipeline 注册表
# ═══════════════════════════════════════════

LAYOUT_PIPELINE_DEFS = [
    (
        "layout", LAYOUT_DET_TEMPLATE, "npu:0",
        config.LAYOUT_DET_MODEL_DIR, "PP-DocLayoutV3",
    ),
]


class PipelineNotReady(Exception):
    """请求的 pipeline 未就绪"""

    def __init__(self, key: str, status: dict):
        self.key = key
        self.available = [k for k, v in status.items() if v == "ready"]
        super().__init__(
            f"Pipeline '{key}' not ready. Available: {self.available}"
        )


class PipelineManager:
    """管理所有 pipeline 的生命周期"""

    def __init__(self):
        self._pipelines: dict[str, BasePipeline] = {}
        self._status: dict[str, str] = {}

    @staticmethod
    def _get_compatible_om_model_dir(model_dir: str) -> str:
        """Return a one-input OM model view when a static backup is available.

        PaddleX's text-recognition predictor submits only the image tensor.  OM
        models compiled with ``--dynamic_batch_size`` expose an additional
        ``ascend_mbatch_shape_data`` control input, which PaddleX does not
        provide.  The deployment package keeps the compatible static model as
        ``inference.om.bak1``; expose it under the normal filename without
        mutating the mounted model directory.
        """
        source_dir = Path(model_dir)
        backup = source_dir / "inference.om.bak1"
        config_file = source_dir / "inference.yml"
        if not backup.is_file() or not config_file.is_file():
            return model_dir

        digest = hashlib.sha256(str(backup.resolve()).encode()).hexdigest()[:16]
        staged_dir = Path("/tmp/ppocr-compatible-om") / digest
        staged_dir.mkdir(parents=True, exist_ok=True)
        for source, target_name in (
            (backup, "inference.om"),
            (config_file, "inference.yml"),
        ):
            target = staged_dir / target_name
            if target.exists() or target.is_symlink():
                if target.resolve() == source.resolve():
                    continue
                target.unlink()
            target.symlink_to(source)
        return str(staged_dir)

    def _build(self, template, device, det_dir, rec_dir, det_name, rec_name):
        """从模板构建 pipeline"""
        cfg = copy.deepcopy(template)

        det = cfg["SubModules"]["TextDetection"]
        det["model_name"] = det_name
        det["model_dir"] = det_dir

        rec = cfg["SubModules"]["TextRecognition"]
        rec["model_name"] = rec_name
        rec["model_dir"] = (
            self._get_compatible_om_model_dir(rec_dir)
            if device.startswith("npu")
            else rec_dir
        )
        rec["score_thresh"] = config.OCR_REC_SCORE_THRESHOLD

        return create_pipeline(config=cfg, device=device, use_hpip=True)

    def _build_layout(self, template, device, model_dir, model_name):
        """从模板构建版面检测 pipeline (OM/NPU)"""
        cfg = copy.deepcopy(template)
        cfg["SubModules"]["ObjectDetection"]["model_name"] = model_name
        cfg["SubModules"]["ObjectDetection"]["model_dir"] = model_dir or None
        return create_pipeline(config=cfg, device=device, use_hpip=True)

    def preload_all(self):
        """服务启动时调用，预加载全部 pipeline"""
        # ── 版面检测 pipeline (OM/NPU) ──
        for key, template, device, model_dir, model_name in LAYOUT_PIPELINE_DEFS:
            try:
                t0 = time.time()
                self._pipelines[key] = self._build_layout(
                    template, device, model_dir, model_name
                )
                self._status[key] = "ready"
                print(f"[{time.time()-t0:.1f}s] ✅ {key}")
            except Exception as e:
                self._status[key] = f"error: {e}"
                print(f"[FAIL] ❌ {key} — {e}")

        # ── OCR pipelines ──
        for key, template, device, det_dir, rec_dir, det_name, rec_name in PIPELINE_DEFS:
            try:
                t0 = time.time()
                self._pipelines[key] = self._build(
                    template, device, det_dir, rec_dir, det_name, rec_name
                )
                self._status[key] = "ready"
                print(f"[{time.time()-t0:.1f}s] ✅ {key}")
            except Exception as e:
                self._status[key] = f"error: {e}"
                print(f"[FAIL] ❌ {key} — {e}")

    def get(self, version: str, backend: str) -> BasePipeline:
        """获取已就绪的 pipeline，未就绪则抛异常"""
        key = f"{version}:{backend}"
        if self._status.get(key) != "ready":
            raise PipelineNotReady(key, self._status)
        return self._pipelines[key]

    def get_layout(self) -> BasePipeline:
        """获取版面检测 pipeline，未就绪则返回 None"""
        key = "layout"
        if self._status.get(key) == "ready":
            return self._pipelines[key]
        return None

    def health(self) -> dict:
        return {
            "status": "ok" if any(v == "ready" for v in self._status.values())
            else "degraded",
            "pipelines": self._status,
        }
