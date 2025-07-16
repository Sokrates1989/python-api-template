# Use the official Python base image
FROM python:3.13-slim

# Bake Image tag into the image.
ARG IMAGE_TAG=local_docker
ENV IMAGE_TAG=$IMAGE_TAG

# Set the working directory in the container
WORKDIR /app

# Copy PDM project files
COPY pyproject.toml pdm.lock ./

RUN apt-get update && apt-get install -y \
    gobject-introspection \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf2.0-dev \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install PDM and project dependencies
RUN pip install pdm && pdm install --prod

# Copy the application code to the container
COPY . .

# Expose the port that the FastAPI application will run on
EXPOSE 8000

# Start the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

