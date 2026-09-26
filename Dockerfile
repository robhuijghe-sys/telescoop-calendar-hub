FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python tests/smoke.py
RUN python tests/calendar_smoke.py
RUN python tests/live_ui_smoke.py
RUN python tests/public_post_smoke.py
RUN python tests/snapshot_smoke.py
RUN python tests/parser_title_smoke.py
RUN python tests/delete_flow_smoke.py
RUN python tests/simple_editor_smoke.py
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "app.simple_calendar:app", "--host", "0.0.0.0", "--port", "8000"]

RUN python tests/day_source_smoke.py

RUN python tests/day_order_smoke.py
