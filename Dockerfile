# Use the official Python base image
FROM python:3.13-slim

# Bake Image tag into the image.
ARG IMAGE_TAG=local_docker
ENV IMAGE_TAG=$IMAGE_TAG

# Set the working directory in the container
WORKDIR /app

# Copy only dependency files first for better build caching
COPY pyproject.toml pdm.lock ./

# Install PDM and project dependencies (creates a fresh .venv)
RUN pip install pdm && pdm install --prod

# Now copy the rest of the application code
COPY app/ .

# Expose the port that the FastAPI application will run on
EXPOSE 8000

# Use 'pdm run' to execute uvicorn from within the project's virtual environment.
ENTRYPOINT ["pdm", "run"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

