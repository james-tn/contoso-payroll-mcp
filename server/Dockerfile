# Contoso Payroll MCP server — container image for Azure Container Apps.
# Pure-Python deps only (no compiled wheels), so the build is fast and reliable.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAYROLL_MCP_HOST=0.0.0.0 \
    PAYROLL_MCP_PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY payroll_mcp ./payroll_mcp
COPY pyproject.toml ./

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# The module-level `app = build_app()` in payroll_mcp/server.py is the ASGI entry point.
CMD ["python", "-m", "uvicorn", "payroll_mcp.server:app", "--host", "0.0.0.0", "--port", "8000"]
