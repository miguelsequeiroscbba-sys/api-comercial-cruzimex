# Usamos una imagen oficial ligera de Python
FROM python:3.9-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar las librerías necesarias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la API y los archivos .joblib generados
COPY main.py .
COPY *.joblib ./

# Exponer el puerto por el que corre la API
EXPOSE 8000

# Comando para encender el servidor automáticamente al iniciar el contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]