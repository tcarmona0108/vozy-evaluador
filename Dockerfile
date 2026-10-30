FROM python:3.12-slim

# Hugging Face Spaces ejecuta el contenedor con UID 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False
WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Solo lo que el servicio necesita (eval/ y la referencia manual quedan fuera, ver .dockerignore).
COPY --chown=user app ./app
COPY --chown=user data ./data

# Render (y otras plataformas) inyectan PORT; 7860 es el valor por defecto.
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips '*'"]
