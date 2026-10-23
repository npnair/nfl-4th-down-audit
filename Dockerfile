FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt dashboard/requirements.txt ./reqs/
RUN pip install --no-cache-dir -r reqs/requirements.txt -r reqs/dashboard/requirements.txt
COPY . .
