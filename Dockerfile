FROM vllm/vllm-openai:latest

# base image entrypoints straight into the vllm api server; we start it ourselves in run.sh
ENTRYPOINT []
WORKDIR /app

RUN pip install --no-cache-dir peft fastapi uvicorn httpx

COPY bake_loras.py gateway.py demo.py run.sh ./

# model weights and baked adapters stay on a mounted volume, not in the image
VOLUME /root/.cache/huggingface /app/adapters
EXPOSE 8080

CMD ["bash", "run.sh"]
