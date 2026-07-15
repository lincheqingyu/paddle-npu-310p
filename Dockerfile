# This base image already contains the tested Ascend/PaddleX runtime and OCR
# model assets under /models. The service layer below only adds this repository.
FROM crpi-qiahktgmz4byhikw.cn-hangzhou.personal.cr.aliyuncs.com/lcqy_docker/paddle-npu-310p:dev-2

LABEL org.opencontainers.image.source="https://github.com/lincheqingyu/paddle-npu-310p"
LABEL org.opencontainers.image.description="PP-OCR FastAPI service with Ascend NPU support"

WORKDIR /app

# Copy only the modules needed at runtime. This keeps repository metadata,
# documentation, examples, and generated analysis artifacts out of the image.
COPY main.py config.py /app/
COPY routers /app/routers
COPY schemas /app/schemas
COPY services /app/services
COPY utils /app/utils

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Load the Ascend runtime paths required by the OM backend before starting.
CMD ["/bin/bash", "-c", "source /etc/profile.d/ascend_env.sh && exec python main.py"]
