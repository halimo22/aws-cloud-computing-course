# Reference solution for Lab 6: single-stage build.
# Copy this file and .dockerignore into app/, then:
#   docker build -t dockerlab:single .

# FROM picks the base image. Every image starts from one.
# slim = Debian with Python and little else (no compilers, no curl).
FROM python:3.12-slim

# ENV sets environment variables for later build steps and for the running
# container. docker run -e GREETING=... overrides them.
ENV GREETING="Hello from a container" \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1

# WORKDIR sets the folder for every instruction after it (created if missing).
WORKDIR /app

# Copy only the dependency list, so the install layer below comes from the
# cache until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The code changes most often, so it is copied last.
# .dockerignore keeps secrets and junk out of this copy.
COPY . .

# VOLUME marks /data as a mount point for data that must outlive the container.
VOLUME /data


# ARG is a build-time variable: docker build --build-arg APP_VERSION=1.1 .
# It is gone after the build, so we copy it into an ENV. It sits late in the
# file because changing it invalidates the cache for the steps after it.
ARG APP_VERSION=1.0
ENV APP_VERSION=$APP_VERSION

# LABEL adds metadata to the image. Read it with docker inspect.
LABEL org.opencontainers.image.title="dockerfile-lab" \
      org.opencontainers.image.version=$APP_VERSION

# EXPOSE documents the port the app listens on. It does not publish it: use -p.
EXPOSE 8000

# HEALTHCHECK: Docker runs this inside the container and marks it healthy
# or unhealthy. The slim image has no curl, so we use Python.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]

# CMD is the default command when the container starts (exec form, no shell).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
