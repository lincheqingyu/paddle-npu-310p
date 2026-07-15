# PP-OCR Service

基于 PaddleX 3.7 的 OCR 推理服务，支持 PP-OCRv5/v6 两条产线，OM（NPU）和 CPU 双后端。

## 目录

```
/app/
├── main.py                     ← FastAPI 入口，/health
├── config.py                   ← 环境变量 → 配置
├── .env.example                ← 环境变量文档
├── requirements.txt
├── routers/
│   └── ocr.py                  ← POST /api/ppocr/files, /api/ppocr/url
├── services/
│   └── pipeline_manager.py     ← 模型预加载 + 版面检测 pipeline
├── schemas/
│   └── ocr.py                  ← Pydantic 模型
└── utils/
    └── image.py                ← 文件解码 + URL 下载
```

## 环境变量

### 加载优先级

```
系统环境变量 (docker run -e)  >  .env 文件  >  代码默认值
```

- **本地开发**：`python main.py`，自动读 `/app/.env`
- **容器部署**：`docker run -e` 或 `--env-file` 传参，会覆盖 `.env` 的值
- **什么都不传**：使用代码里的默认值

### 变量列表

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OCR_V5_DET_OM_DIR` | `/models/om/PP-OCRv5_server_det` | v5 OM 检测模型目录 |
| `OCR_V5_REC_OM_DIR` | `/models/om/PP-OCRv5_server_rec` | v5 OM 识别模型目录 |
| `OCR_V6_DET_OM_DIR` | `/models/om/ppocrv6_medium_det` | v6 OM 检测模型目录 |
| `OCR_V6_REC_OM_DIR` | `/models/om/ppocrv6_medium_rec` | v6 OM 识别模型目录 |
| `OCR_V5_DET_ONNX_DIR` | `/models/onnx/PP-OCRv5_server_det` | v5 CPU 检测模型目录 |
| `OCR_V5_REC_ONNX_DIR` | `/models/onnx/PP-OCRv5_server_rec` | v5 CPU 识别模型目录 |
| `OCR_V6_DET_ONNX_DIR` | `/models/onnx/ppocrv6_medium_det` | v6 CPU 检测模型目录 |
| `OCR_V6_REC_ONNX_DIR` | `/models/onnx/ppocrv6_medium_rec` | v6 CPU 识别模型目录 |
| `LAYOUT_DET_MODEL_DIR` | `/models/.paddlex/official_models/PP-DocLayoutV3` | PP-DocLayoutV3 版面检测模型目录 |
| `OCR_REC_SCORE_THRESHOLD` | `0.8` | 识别置信度阈值，低于此分的文本不显示 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8080` | 监听端口 |

## API

### `GET /health`

```json
{
  "status": "ok",
  "pipelines": {
    "v5:om": "ready",
    "v5:cpu": "ready",
    "v6:om": "ready",
    "v6:cpu": "ready"
  },
  "npu_available": true
}
```

### `POST /api/ppocr/files`

上传图片文件进行 OCR 识别。路径由原 `/api/ppocr` 重命名而来。

请求（`multipart/form-data`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `files` | `file[]` | 上传的图片文件，1-20 张 |
| `version` | `"v5"` / `"v6"` | 模型产线版本 |
| `backend` | `"om"` / `"cpu"` | om=NPU, cpu=ONNX Runtime |

响应：

```json
{
  "results": [
    {
      "texts": ["文字1", "文字2"],
      "scores": [0.99, 0.95],
      "boxes": [[12, 34, 100, 56], [12, 60, 100, 82]]
    }
  ],
  "version": "v5",
  "backend": "om",
  "elapsed": 2.86
}
```

> **注意**：`OCR_REC_SCORE_THRESHOLD`（默认 0.8）以下的识别结果已被 pipeline 内部过滤，不会出现在响应中。

### `POST /api/ppocr/url`

通过图片 URL 进行 OCR 识别，自动运行版面分析（PP-DocLayoutV3）区分标题与正文。

请求（`application/json`）：

```json
{
  "images": ["https://example.com/doc.png"],
  "version": "v5",
  "backend": "cpu"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `images` | `string[]` | 图片 URL 列表，1-20 张 |
| `version` | `"v5"` / `"v6"` | 模型产线版本 |
| `backend` | `"om"` / `"cpu"` | om=NPU, cpu=ONNX Runtime |

响应：

```json
{
  "results": [
    {
      "title": "文档标题",
      "body": "第一行正文\n第二行正文\n第三行正文",
      "ocr_time": 2.86,
      "file_url": "https://example.com/doc.png",
      "file_type": "image/png"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | `string` | 文档标题（来自版面分析的 doc_title/paragraph_title 区域） |
| `body` | `string` | 文档正文，以 `\n` 分行 |
| `ocr_time` | `float` | 单张图片处理耗时（秒） |
| `file_url` | `string` | 原图 URL |
| `file_type` | `string` | 图片 MIME 类型 |

## 启动

```bash
cd /app
python main.py
```

或：

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

## 扩展

新增产线只需改三个文件：

1. `config.py` — 加模型路径
2. `services/pipeline_manager.py` — 加模板 + 注册项（OCR 用 `_build`，版面检测用 `_build_layout`）
3. `routers/` — 如需新接口 shape，加路由

已集成 PP-DocLayoutV3 版面分析模型，通过 `object_detection` pipeline 独立运行（CPU，`use_hpip=False`），与 OCR pipeline 解耦。OCR 结果通过 IoU 匹配到版面区域，自动区分标题/正文。
