# Usa la imagen base oficial de Python
FROM python:3.9-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de la aplicación al contenedor
COPY . /app

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Exponer el puerto 8080, que es el puerto por defecto para Cloud Run
EXPOSE 8080

# Establece la variable de entorno para indicar que la app escuchará en el puerto correcto
ENV PORT=8080

# Comando para ejecutar la app Flask
CMD ["python", "app.py"]
