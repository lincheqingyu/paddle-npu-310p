"""
PP-OCR 服务入口
启动时预加载全部 pipeline，通过 /health 和 /api/ppocr 提供服务。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import config
from services.pipeline_manager import PipelineManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 启动：预加载所有 pipeline ──
    print("=" * 50)
    print("Preloading pipelines...")
    manager = PipelineManager()
    manager.preload_all()
    app.state.manager = manager
    print("=" * 50)
    loaded = sum(1 for v in manager.health()["pipelines"].values() if v == "ready")
    print(f"Ready: {loaded}/{len(manager.health()['pipelines'])} pipelines loaded")
    yield
    # ── 关闭：无需清理 ──


app = FastAPI(
    title="PP-OCR Service",
    description="Layout-first OCR service with OM (Ascend NPU) and ONNX Runtime backends.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """返回所有 pipeline 状态，om 管线 ready 即表示 NPU 可用"""
    manager = app.state.manager  # type: ignore[attr-defined]
    return manager.health()


from routers.ocr import router  # noqa: E402
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
