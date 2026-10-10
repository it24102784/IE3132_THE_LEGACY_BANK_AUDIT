FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	DASHBOARD_PORT=80

WORKDIR /app/dashboard
COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/ ./
COPY flags/ /app/flags/

EXPOSE 80
CMD ["sh", "-c", "python seed.py && exec python app.py"]