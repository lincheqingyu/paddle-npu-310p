# PP-OCR Service

基于 PaddleX 3.7 的版面优先 OCR 服务，支持 PP-OCRv5/v6、OM（Ascend NPU）和 ONNX Runtime（CPU）后端。每张图片先经 PP-DocLayoutV3 进行版面检测，再对每个区域独立 OCR；版面检测不可用或未检测到区域时，会回退为整图 OCR。

## API

服务监听 `0.0.0.0:8080`，提供以下接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 查询全部 pipeline 的就绪状态 |
| `POST` | `/api/ppocr/files` | 上传 1-20 张图片进行 OCR |
| `POST` | `/api/ppocr/url` | 提交 1-20 个图片 URL 进行 OCR |

### `GET /health`

所有 pipeline 均加载成功时，响应如下。任一 pipeline 失败时，其值为 `error: ...`；没有可用 pipeline 时，`status` 为 `degraded`。

```json
{
  "status": "ok",
  "pipelines": {
    "layout": "ready",
    "v5:om": "ready",
    "v5:cpu": "ready",
    "v6:om": "ready",
    "v6:cpu": "ready"
  }
}
```

### `POST /api/ppocr/files`

请求为 `multipart/form-data`。`files` 可重复传递以提交多张图片，`version` 与 `backend` 为必填字段。

| 字段 | 类型 | 取值 | 说明 |
| --- | --- | --- | --- |
| `files` | `file[]` | 1-20 张图片 | 待识别图片 |
| `version` | string | `v5`、`v6` | OCR 产线 |
| `backend` | string | `om`、`cpu` | `om` 为 NPU，`cpu` 为 ONNX Runtime |

```bash
curl -X POST http://127.0.0.1:8080/api/ppocr/files \
  -F 'files=@document.png' \
  -F 'version=v5' \
  -F 'backend=om'
```

### `POST /api/ppocr/url`

请求为 JSON：

```json
{
  "images": ["https://example.com/document.png"],
  "version": "v6",
  "backend": "cpu"
}
```

两个 OCR 接口使用相同的响应格式：

```json
{
  "results": [
    {
      "blocks": [
        {
          "label": "doc_title",
          "label_name": "文档标题",
          "bbox": [40, 32, 860, 108],
          "content": "示例文档标题",
          "confidence": 0.9912,
          "lines": [
            {
              "text": "示例文档标题",
              "score": 0.9987,
              "bbox": [55, 46, 410, 91]
            }
          ]
        }
      ],
      "version": "v5",
      "backend": "om",
      "elapsed": 0.842,
      "file_url": "",
      "file_type": "image/png"
    }
  ]
}
```

`/files` 的 `file_url` 为空字符串；`/url` 的 `file_url` 为请求中的图片 URL。`bbox` 为 `[x1, y1, x2, y2]`，坐标相对于原图。`content` 由该区域的 OCR 文本按换行拼接，`lines` 保留逐行文本、置信度和坐标。

无效图片或 URL 下载失败返回 `400`。请求的 OCR pipeline 未就绪或推理失败返回 `503`。

## 环境变量

优先级为：系统环境变量 > `.env` 文件 > 代码默认值。容器部署可用 `docker run -e NAME=value` 覆盖默认值。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OCR_V5_DET_OM_DIR` | `/models/om/PP-OCRv5_server_det` | v5 OM 检测模型目录 |
| `OCR_V5_REC_OM_DIR` | `/models/om/PP-OCRv5_server_rec` | v5 OM 识别模型目录 |
| `OCR_V6_DET_OM_DIR` | `/models/om/ppocrv6_medium_det` | v6 OM 检测模型目录 |
| `OCR_V6_REC_OM_DIR` | `/models/om/ppocrv6_medium_rec` | v6 OM 识别模型目录 |
| `OCR_V5_DET_ONNX_DIR` | `/models/onnx/PP-OCRv5_server_det` | v5 CPU 检测模型目录 |
| `OCR_V5_REC_ONNX_DIR` | `/models/onnx/PP-OCRv5_server_rec` | v5 CPU 识别模型目录 |
| `OCR_V6_DET_ONNX_DIR` | `/models/onnx/ppocrv6_medium_det` | v6 CPU 检测模型目录 |
| `OCR_V6_REC_ONNX_DIR` | `/models/onnx/ppocrv6_medium_rec` | v6 CPU 识别模型目录 |
| `LAYOUT_DET_MODEL_DIR` | `/models/om/PP-DocLayoutV3` | PP-DocLayoutV3 OM 模型目录 |
| `OCR_REC_SCORE_THRESHOLD` | `0.8` | OCR 识别分数阈值 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8080` | 监听端口 |

## 容器构建与运行

基础镜像已包含 `/models`、PaddleX 和 Ascend runtime。Dockerfile 会在服务启动前加载 `/etc/profile.d/ascend_env.sh`，因此不要使用 `docker commit`，也不需要在运行时挂载模型目录。

```bash
docker build --pull=false \
  -t crpi-qiahktgmz4byhikw.cn-hangzhou.personal.cr.aliyuncs.com/lcqy_docker/paddle-npu-310p:1.0.1-cann800 \
  .

docker run -d \
  --name paddle-npu-service \
  --privileged \
  --network=host \
  --ipc=host \
  --shm-size=128G \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi:ro \
  -v /usr/local/dcmi:/usr/local/dcmi:ro \
  crpi-qiahktgmz4byhikw.cn-hangzhou.personal.cr.aliyuncs.com/lcqy_docker/paddle-npu-310p:1.0.1-cann800
```

启动时会预加载 5 个 pipeline。检查日志和服务状态：

```bash
docker logs -f paddle-npu-service
curl -f http://127.0.0.1:8080/health
```
