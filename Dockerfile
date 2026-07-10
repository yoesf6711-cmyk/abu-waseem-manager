FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
ENV PORT=5000
EXPOSE 5000
CMD ["gunicorn","-b","0.0.0.0:5000","app:app"]
