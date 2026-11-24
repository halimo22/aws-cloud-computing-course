"""Tiny web app for the Dockerfile lab.

so you can see what your Dockerfile changed by calling the app.
"""



import os
import platform
import pwd
import socket
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)


def current_user():
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:  # a --user id with no account in the image
        return str(os.getuid())


@app.get("/")
def index():
    return jsonify(
        message=os.environ.get("GREETING", "Hello from Python"),  # ENV
        version=os.environ.get("APP_VERSION", "dev"),  # ARG copied into ENV
        python=platform.python_version(),  # FROM (the base image)
        workdir=os.getcwd(),  # WORKDIR
        user=current_user(),  # USER
        hostname=socket.gethostname(),  # the container ID
    )


@app.get("/visits")
def visits():
    counter = Path(os.environ.get("DATA_DIR", "/data")) / "visits.txt"  # VOLUME
    counter.parent.mkdir(parents=True, exist_ok=True)
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    return jsonify(visits=count, stored_in=str(counter))


@app.get("/health")
def health():  # HEALTHCHECK
    return jsonify(status="ok")
