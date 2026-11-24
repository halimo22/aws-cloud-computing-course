# Lab 6: Docker and the Dockerfile

## Session overview

Students learn what each Dockerfile instruction does by containerizing a small Python web app. They start from a Dockerfile that works but is wasteful: it is huge, rebuilds everything on each code change, runs as root, and leaks a secret. They then fix it one instruction at a time and measure the result. The app is written so that each field it returns shows the effect of one instruction, so students can see what their Dockerfile changed by calling it.

Plan about 50 minutes of theory (Part 1) and about 110 minutes of hands-on work (Part 2). This lab fits Week 7 (Docker fundamentals) of the [12-week program](../course-plan/12-week-program.pdf). Do it before [Lab 5](../lab-05-containers-ecr-ecs/), which pushes images like this one to ECR and runs them on ECS.

**Prerequisites**

- A place to run Docker. **AWS CloudShell** includes Docker and Git, so nothing is installed. Docker Desktop on a laptop also works.
- Basic Linux commands (`cd`, `ls`, `cat`) and basic HTTP (`curl`).
- No Python knowledge is needed. You read the app; you do not change it.

**Learning outcomes.** By the end, a student can:

- Explain images, layers, containers, and the build context.
- Explain what each common Dockerfile instruction does, and whether it acts at build time or at run time.
- Order instructions so that the layer cache works for you, and measure the difference.
- Keep secrets and junk out of an image with `.dockerignore`, and prove it.
- Configure an image with `ENV` and `ARG`, and explain the difference.
- Run a container as a non-root user, with a volume it can write to.
- Add a `HEALTHCHECK`, and read a container's health.
- Explain `CMD` vs `ENTRYPOINT`, and override each one.
- Write a multi-stage build, and choose a base image.
- Inspect an image with `docker history` and `docker inspect`.

**Timing**

| Block | Minutes |
| --- | --- |
| Part 1: images, layers, and the Dockerfile instructions (theory) | 50 |
| Steps 1 to 2: the bad Dockerfile, then base image, WORKDIR, and caching | 30 |
| Steps 3 to 4: `.dockerignore`, `ENV`, `ARG`, `LABEL`, `EXPOSE` | 25 |
| Steps 5 to 6: `USER`, `VOLUME`, `HEALTHCHECK` | 25 |
| Steps 7 to 8: `CMD` vs `ENTRYPOINT`, multi-stage build | 20 |
| Step 9: results table, discussion, and cleanup | 10 |

**What we build**

```
Step 1 (bad)                                  Step 8 (final)
python:3.12, everything in /,         -->     python:3.12-slim, multi-stage,
root user, secret inside, ~1.6 GB             non-root user, volume, healthcheck,
                                              no secret, ~210 MB
```

**The files**

```
lab-06-docker-dockerfile/
  app/
    app.py              the web app (Flask, served by gunicorn)
    requirements.txt    its two dependencies
  solution/
    Dockerfile             final single-stage Dockerfile, every line commented
    Dockerfile.multistage  final multi-stage Dockerfile, every line commented
    .dockerignore          files kept out of the image
```

**The app**

[app/app.py](app/app.py) has three endpoints. Each field maps to a Dockerfile instruction:

| Endpoint | Field | Shows the effect of |
| --- | --- | --- |
| `/` | `python` | `FROM` (the Python version comes from the base image) |
| `/` | `workdir` | `WORKDIR` |
| `/` | `message` | `ENV GREETING`, overridden with `docker run -e` |
| `/` | `version` | `ARG APP_VERSION`, copied into an `ENV` |
| `/` | `user` | `USER` |
| `/` | `hostname` | The container ID: every container gets its own |
| `/visits` | `visits` | `VOLUME`: a counter saved in `/data/visits.txt` |
| `/health` | `status` | `HEALTHCHECK` calls this |

---

## Part 1: Images, layers, and the Dockerfile

### The problem a container solves

"It works on my machine" happens because a program depends on more than its code: a language version, libraries, OS packages, environment variables, file paths. A **container image** packages all of that into one file system. A **container** is a running process started from an image, isolated from other processes but sharing the host's kernel. The same image runs the same way on a laptop, in CloudShell, and on ECS.

| | Virtual machine | Container |
| --- | --- | --- |
| Contains | A full OS with its own kernel | The app and its user-space files only |
| Starts in | Minutes | Seconds or less |
| Size | Gigabytes | Megabytes to a few hundred MB |
| Isolation | Strong: separate kernel | Weaker: shared kernel, separated by namespaces and cgroups |

### Images and layers

An image is a stack of read-only **layers**. Each `RUN`, `COPY`, or `ADD` instruction adds one layer that holds the files it changed. Other instructions (`ENV`, `CMD`, `EXPOSE`, and so on) change only the image's settings, not its files. When a container starts, Docker adds a thin **writable layer** on top. Anything the container writes goes there, and is lost when the container is removed, unless it is written to a **volume**.

```
+---------------------------------+  <- container writable layer (deleted with the container)
+---------------------------------+  <- COPY . .                    (your code: changes often)
+---------------------------------+  <- RUN pip install ...         (dependencies)
+---------------------------------+  <- COPY requirements.txt .
+---------------------------------+  <- python:3.12-slim layers     (OS files and Python)
```

### The build context

`docker build -t name .` sends the folder `.` (the **build context**) to the Docker builder. `COPY` can only copy files from the build context. Everything in the folder is sent unless `.dockerignore` excludes it, including `.git`, virtual environments, and `.env` files with passwords. Anything sent can end up in the image.

### The layer cache

Docker reuses a layer from an earlier build if the instruction is the same, the layer below it is the same, and (for `COPY` and `ADD`) the copied files have the same content. **Once one layer misses the cache, every layer after it is rebuilt.** That gives the most useful rule in this lab:

> Put the things that change rarely at the top, and the things that change often at the bottom.

Dependencies change rarely and are slow to install. Code changes often and is fast to copy. So copy `requirements.txt` and install first, then copy the code.

### The instructions

| Instruction | What it does | Acts at | Example from this lab |
| --- | --- | --- | --- |
| `FROM` | Picks the base image. Starts a new build stage. | Build | `FROM python:3.12-slim` |
| `WORKDIR` | Sets the working folder for the instructions after it, and for the running container. Creates it if missing. | Build and run | `WORKDIR /app` |
| `COPY` | Copies files from the build context (or `--from` another stage) into the image. | Build | `COPY requirements.txt .` |
| `ADD` | Like `COPY`, but can also fetch URLs and unpack local tar files. Prefer `COPY` unless you need those. | Build | (not used) |
| `RUN` | Runs a command while building, and saves the result as a layer. | Build | `RUN pip install --no-cache-dir -r requirements.txt` |
| `ENV` | Sets an environment variable for later build steps **and** for the running container. | Build and run | `ENV GREETING="Hello from a container"` |
| `ARG` | Declares a variable that exists **only while building**. Set it with `--build-arg`. | Build | `ARG APP_VERSION=1.0` |
| `LABEL` | Adds metadata (key and value) to the image. | Metadata | `LABEL org.opencontainers.image.version=1.0` |
| `EXPOSE` | Documents the port the app listens on. It does **not** open or publish it. | Metadata | `EXPOSE 8000` |
| `USER` | Sets the user for later `RUN` instructions and for the running container. | Build and run | `USER appuser` |
| `VOLUME` | Marks a folder as a mount point for data that must outlive the container. | Run | `VOLUME /data` |
| `HEALTHCHECK` | A command Docker runs inside the container to decide if it is healthy. | Run | `HEALTHCHECK CMD python -c "..."` |
| `CMD` | The default command when the container starts. Replaced by any command given to `docker run`. | Run | `CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]` |
| `ENTRYPOINT` | The fixed program the container runs. `CMD` becomes its default arguments. | Run | `ENTRYPOINT ["echo", "Hello,"]` |

Less common: `SHELL` (change the shell used by `RUN`), `STOPSIGNAL` (signal sent by `docker stop`), `ONBUILD` (instructions for images built on top of this one).

### Exec form vs shell form

`RUN`, `CMD`, `ENTRYPOINT`, and `HEALTHCHECK CMD` can be written two ways:

| Form | Example | What happens |
| --- | --- | --- |
| Exec form (JSON list) | `CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]` | The program is started directly as process 1. It receives `docker stop`'s signal and shuts down cleanly. `$VARIABLES` are **not** expanded. |
| Shell form (plain text) | `CMD gunicorn --bind 0.0.0.0:8000 app:app` | Runs as `/bin/sh -c "..."`. `$VARIABLES` are expanded, but the shell may not pass signals on, so `docker stop` can wait 10 seconds and then kill it. |

Use exec form for `CMD` and `ENTRYPOINT`. Shell form is normal for `RUN`, where you want `&&` and variables.

### CMD vs ENTRYPOINT

| Dockerfile has | `docker run image` runs | `docker run image X` runs |
| --- | --- | --- |
| `CMD ["a"]` only | `a` | `X` (CMD is replaced) |
| `ENTRYPOINT ["e"]` only | `e` | `e X` |
| `ENTRYPOINT ["e"]` and `CMD ["a"]` | `e a` | `e X` (only the arguments are replaced) |

`docker run --entrypoint P image` replaces the entrypoint. Most web apps use only `CMD`. Use `ENTRYPOINT` when the image is a tool that always runs one program, such as a command-line utility.

### ARG vs ENV

| | `ARG` | `ENV` |
| --- | --- | --- |
| Set with | `docker build --build-arg NAME=value` | `docker run -e NAME=value` (overrides the default) |
| Exists during the build | Yes | Yes |
| Exists in the running container | No (unless copied into an `ENV`) | Yes |
| Typical use | Version numbers, base image tags | App configuration: ports, log level, greeting |
| Safe for secrets | **No**: shown by `docker history` | **No**: shown by `docker inspect` |

### Choosing a base image

| Base image | Size (approx.) | Has | Trade-off |
| --- | --- | --- | --- |
| `python:3.12` | ~1 to 1.6 GB | Debian, compilers, headers, many tools | Builds anything. Large, and more software to patch. Good as a **build** stage. |
| `python:3.12-slim` | ~130 to 200 MB | Debian with only what Python needs | The usual choice. No compilers and no `curl`. |
| `python:3.12-alpine` | ~50 to 60 MB | Alpine Linux (musl libc) | Smallest, but many Python packages have no ready-made wheels for musl, so builds are slower and can behave differently. |
| Distroless | ~50 MB | Python and your app, no shell, no package manager | Smallest attack surface, but hard to debug: you cannot `docker exec` a shell. |

Pin a version (`3.12-slim`, not `latest`) so a rebuild next month gives the same Python. Sizes vary with the CPU type and with how Docker counts them: Docker Desktop usually reports larger numbers than CloudShell for the same image.

### Multi-stage builds

A Dockerfile can have several `FROM` lines. Each starts a new **stage**, and only the last stage becomes the image. An earlier stage can use a big image with compilers to build or install things, and the last stage copies only the results with `COPY --from=<stage>`. The compilers never reach the final image.

```
Stage "builder": python:3.12 (~1 GB, has gcc)   -->  pip install into /install
Stage 2:         python:3.12-slim               <--  COPY --from=builder /install /usr/local
                                                     only this stage is shipped
```

### Security rules for Dockerfiles

- **Never put secrets in an image.** Not in a file, not in `ENV`, not in `ARG`. Anyone who can pull the image can read them with `docker history`, `docker inspect`, or by running a shell in it. A file deleted in a later `RUN` still exists in the earlier layer.
- **Use `.dockerignore`** so `.env`, `.git`, and credentials are never sent to the builder.
- **Run as a non-root user.** If the app is broken into, the attacker gets an ordinary user, not root.
- **Install only what you need**, and use a slim base image. Less software means fewer vulnerabilities to patch.
- **Pin versions** of the base image and the dependencies.

### Questions for students

1. Which instructions add a file system layer? (`RUN`, `COPY`, and `ADD`. The others change only settings.)
2. You change one line in `app.py`. With `COPY . .` above `RUN pip install`, what is rebuilt? (The copy and the install, because the install's parent layer changed.)
3. `EXPOSE 8000` is in the Dockerfile, but the browser cannot reach the app. Why? (`EXPOSE` only documents. You still need `-p 8080:8000` on `docker run`.)
4. Where should a database password go: `ENV`, `ARG`, or neither? (Neither. Pass it at run time from a secret store, such as Secrets Manager in Lab 5.)

---

## Part 2: Hands-on lab

### Before you start

1. Open **AWS CloudShell** (the terminal icon in the console's top bar), or a terminal with Docker Desktop running.
2. Check Docker works:

```bash
docker version
```

3. Get the app and move into its folder:

```bash
git clone https://github.com/halimo22/aws-cloud-computing-course.git
cd aws-cloud-computing-course/lab-06-docker-dockerfile/app
ls
```

You should see `app.py` and `requirements.txt`. You write every Dockerfile in this folder. Each step replaces the previous `Dockerfile`.

4. Create a fake secret file, the kind a developer keeps next to the code:

```bash
echo 'DB_PASSWORD=SuperSecret123' > .env
```

5. Read [app.py](app/app.py) for two minutes, and match each field to the table in "The app" above.

CloudShell has no public port, so you test with `curl localhost:8080`. On a laptop you can also open `http://localhost:8080` in a browser.

### Step 1: The bad Dockerfile

Goal: a Dockerfile that works, so we can measure what is wrong with it.

1. Create the Dockerfile:

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12
COPY . .
RUN pip install -r requirements.txt
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
EOF
```

| Line | Meaning |
| --- | --- |
| `FROM python:3.12` | Start from the full Python image. |
| `COPY . .` | Copy everything in the build context into the image's current folder, which is `/`. |
| `RUN pip install ...` | Install Flask and gunicorn while building. |
| `CMD [...]` | When a container starts, run gunicorn on port 8000, serving the `app` object from `app.py`. |

2. Build it, timing the build, and look at its size:

```bash
time docker build -t dockerlab:v1 .
docker images dockerlab
```

3. Run it and call it:

```bash
docker run -d --name v1 -p 8080:8000 dockerlab:v1
curl localhost:8080
```

`-d` runs the container in the background. `-p 8080:8000` publishes the container's port 8000 on the host's port 8080. `--name` gives it a name to use in later commands.

4. Look inside the running container:

```bash
docker exec v1 ls /          # your files are mixed with the OS folders
docker exec v1 cat /.env     # the secret is in the image
docker exec v1 whoami        # root
```

5. Measure a code change. Change the greeting, rebuild, and watch the output:

```bash
sed -i 's/Hello from Python/Hello from Python v1/' app.py
time docker build -t dockerlab:v1 .
```

The `RUN pip install` step runs again, although `requirements.txt` did not change. The code change invalidated the `COPY . .` layer, and every layer after it.

6. Clean up the container:

```bash
docker rm -f v1
```

**Checkpoint.** Write these in your results table (Step 9):

- [ ] Image size (expect around 1 to 1.6 GB).
- [ ] Rebuild time after a code change, and that `pip install` ran again.
- [ ] `curl` shows `"user": "root"` and `"workdir": "/"`.
- [ ] `cat /.env` printed the password.

### Step 2: Slim base image, WORKDIR, and cache-friendly order

Goal: a smaller image that rebuilds in about a second when only the code changes.

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
EOF

time docker build -t dockerlab:v2 .
```

What changed, and why:

| Change | Why |
| --- | --- |
| `python:3.12-slim` | The same Python without compilers and tools, so the image is far smaller. |
| `WORKDIR /app` | The app lives in its own folder, not mixed into `/`. Every later `COPY .` and the running app use `/app`. |
| `COPY requirements.txt .` before `RUN pip install` | The install layer now depends only on `requirements.txt`, so it is reused until the dependency list changes. |
| `--no-cache-dir` | pip does not keep its download cache inside the image. |
| `COPY . .` last | The code changes most often, so it is the only layer rebuilt after a code change. |

1. Change the code again and rebuild:

```bash
sed -i 's/Hello from Python v1/Hello from Python v2/' app.py
time docker build -t dockerlab:v2 .
```

Every step up to `COPY . .` shows `CACHED`. (The older builder prints `Using cache` instead.)

2. Compare sizes and run it:

```bash
docker images dockerlab
docker run -d --name v2 -p 8080:8000 dockerlab:v2
curl localhost:8080        # "workdir": "/app"
docker exec v2 cat .env    # the secret is still there!
docker rm -f v2
```

**Checkpoint**

- [ ] The image is roughly 150 to 230 MB, down from more than 1 GB.
- [ ] A rebuild after a code change takes about a second, with `pip install` cached.
- [ ] `workdir` is `/app`.
- [ ] The `.env` file is still in the image. Step 3 fixes this.

### Step 3: .dockerignore

Goal: keep the secret, and other files that do not belong, out of the build context.

1. Create `.dockerignore` next to the Dockerfile:

```bash
cat > .dockerignore << 'EOF'
.env
*.env
.git
__pycache__/
*.pyc
.venv/
Dockerfile*
.dockerignore
EOF
```

Docker still reads the Dockerfile itself when it is listed here. The file is just not copied into the image.

2. Rebuild with the same Dockerfile, and check:

```bash
docker build -t dockerlab:v3 .
docker run --rm dockerlab:v3 ls -a /app
```

`--rm` deletes the container when its command ends. Giving a command after the image name (`ls -a /app`) replaces `CMD` for this one run.

**Checkpoint**

- [ ] `/app` contains only `app.py` and `requirements.txt`. No `.env`, no `Dockerfile`.

**Important.** `.dockerignore` protects only **future** builds. The `v1` and `v2` images still contain the password. If such an image was ever pushed to a registry, treat the password as leaked and change it.

### Step 4: ENV, ARG, LABEL, and EXPOSE

Goal: configure the image from outside, and describe it.

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12-slim
ENV GREETING="Hello from a container" \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ARG APP_VERSION=1.0
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.title="dockerfile-lab" \
      org.opencontainers.image.version=$APP_VERSION
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
EOF
```

| Instruction | Meaning |
| --- | --- |
| `ENV GREETING=...` | A default greeting, baked into the image and readable by the app. |
| `ENV PYTHONUNBUFFERED=1` | Python prints logs immediately, so `docker logs` shows them at once. |
| `ARG APP_VERSION=1.0` | A build-time variable, with a default. Placed after the slow steps, because changing it invalidates the cache from this line down. |
| `ENV APP_VERSION=$APP_VERSION` | Copies the build-time value into the running container. Without it, the app would see nothing. |
| `LABEL ...` | Metadata about the image. The `org.opencontainers.image.*` keys are a standard. |
| `EXPOSE 8000` | Documents the port. Publishing it is still `-p`. |
| `--access-logfile -` | gunicorn logs each request to standard output, where `docker logs` reads it. |

1. Build twice, with two versions:

```bash
docker build -t dockerlab:1.0 .
docker build -t dockerlab:1.1 --build-arg APP_VERSION=1.1 .
```

2. Run version 1.1 with the default greeting, and version 1.0 with a greeting set at run time:

```bash
docker run -d --name a -p 8080:8000 dockerlab:1.1
docker run -d --name b -p 8081:8000 -e GREETING="Hi from container b" dockerlab:1.0
curl localhost:8080
curl localhost:8081
docker logs b              # the request you just made
```

3. Read the metadata:

```bash
docker inspect dockerlab:1.1 --format '{{json .Config.Labels}}'
docker inspect dockerlab:1.1 --format '{{json .Config.Env}}'
docker inspect dockerlab:1.1 --format '{{json .Config.ExposedPorts}}'
docker history dockerlab:1.1
docker rm -f a b
```

**Checkpoint**

- [ ] Container `a` shows `"version": "1.1"` and the default greeting.
- [ ] Container `b` shows `"version": "1.0"` and your greeting, from an image built without it.
- [ ] `docker history` shows `ARG APP_VERSION=1.1`. Build arguments are recorded in the image, which is why they must never hold secrets.
- [ ] `docker history` shows which lines added size (`RUN`, `COPY`) and which added `0B` (settings only).

### Step 5: USER and VOLUME

Goal: run as a non-root user, and keep data after the container is gone.

**Part A: the first try (broken on purpose)**

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12-slim
ENV GREETING="Hello from a container" \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
USER appuser
ARG APP_VERSION=1.0
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.title="dockerfile-lab" \
      org.opencontainers.image.version=$APP_VERSION
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
EOF

docker build -t dockerlab:v5 .
docker run -d --name v5 -p 8080:8000 dockerlab:v5
curl localhost:8080             # "user": "appuser"
curl -i localhost:8080/visits   # 500 Internal Server Error
docker logs v5 | grep Error
docker exec v5 ls -ld /data
docker rm -f -v v5
```

| Instruction | Meaning |
| --- | --- |
| `RUN useradd ... appuser` | Creates an ordinary user. It is placed early because it never changes, so it stays cached. |
| `VOLUME /data` | `/data` is stored outside the container's writable layer. |
| `USER appuser` | From here on, and when the container runs, processes run as `appuser`, not root. |

The logs show `PermissionError`, and `ls -ld /data` shows the folder belongs to `root`. `VOLUME` created the folder as root, and `appuser` cannot write to it. `-v` on `docker rm` also deletes the container's unnamed volume.

**Part B: the fix**

Create `/data` and give it to `appuser` **before** `VOLUME` and `USER`. Replace the `RUN useradd` line:

```bash
sed -i 's|^RUN useradd --create-home --uid 10001 appuser$|RUN useradd --create-home --uid 10001 appuser \&\& mkdir -p /data \&\& chown appuser /data|' Dockerfile
grep useradd Dockerfile
docker build -t dockerlab:v5 .
```

Now prove the data outlives the container, with a **named volume** called `lab6-data`:

```bash
docker run -d --name v5 -p 8080:8000 -v lab6-data:/data dockerlab:v5
curl localhost:8080/visits      # 1
curl localhost:8080/visits      # 2
docker rm -f v5                 # the container and its writable layer are gone

docker run -d --name v5 -p 8080:8000 -v lab6-data:/data dockerlab:v5
curl localhost:8080/visits      # 3: the counter survived
docker volume ls
docker rm -f v5
```

**Checkpoint**

- [ ] Part A returned a 500, and you can explain why from the logs.
- [ ] After the fix, `/` shows `"user": "appuser"`.
- [ ] The visit counter continued at 3 in a brand-new container.

### Step 6: HEALTHCHECK

Goal: let Docker know whether the app inside is actually working, not just running.

This is the Step 5 Dockerfile with the fix, plus a `HEALTHCHECK` above the `CMD`:

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12-slim
ENV GREETING="Hello from a container" \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /data \
 && chown appuser /data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
USER appuser
ARG APP_VERSION=1.0
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.title="dockerfile-lab" \
      org.opencontainers.image.version=$APP_VERSION
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
EOF
```

| Option | Meaning |
| --- | --- |
| `--interval=30s` | Run the check every 30 seconds. |
| `--timeout=3s` | A check that takes longer than 3 seconds counts as failed. |
| `--start-period=5s` | Failures in the first 5 seconds do not count, so the app has time to start. |
| `--retries=3` | 3 failures in a row mark the container `unhealthy`. |
| `CMD [...]` | The check itself. Exit code 0 is healthy. The slim image has no `curl`, so we use Python, which is already there. |

This is the final single-stage Dockerfile. [solution/Dockerfile](solution/Dockerfile) is the same file with a comment on every line. Build and run it:

```bash
docker build -t dockerlab:v6 .
docker run -d --name v6 -p 8080:8000 dockerlab:v6
docker ps                        # STATUS shows (health: starting), then (healthy)
docker inspect v6 --format '{{json .State.Health}}'
docker logs v6                   # after a few seconds, health checks appear as GET /health requests
```

Now make one unhealthy. Start a container whose command is replaced so gunicorn listens on port 9000, while the health check still calls port 8000. `--health-interval 5s` speeds up the check for this demo:

```bash
docker run -d --name sick --health-interval 5s dockerlab:v6 gunicorn --bind 0.0.0.0:9000 app:app
sleep 30
docker ps                        # sick shows (unhealthy), but it is still "Up"
docker rm -f v6 sick
```

**Checkpoint**

- [ ] `v6` became `healthy`.
- [ ] `sick` became `unhealthy`. Docker reports it but does not restart it. Orchestrators such as ECS use the health status to replace the container.

### Step 7: CMD vs ENTRYPOINT

Goal: see which part of the start command can be replaced, and how.

Build a tiny separate image. `-f` picks a Dockerfile with another name:

```bash
cat > Dockerfile.greet << 'EOF'
FROM python:3.12-slim
ENTRYPOINT ["echo", "Hello,"]
CMD ["world"]
EOF

docker build -f Dockerfile.greet -t greet .
docker run --rm greet                      # Hello, world
docker run --rm greet class                # Hello, class   (CMD replaced)
docker run --rm --entrypoint date greet    # the date       (ENTRYPOINT replaced)
```

Now try the same on the app image, which has only `CMD`:

```bash
docker run --rm dockerlab:v6 python -c "print('CMD replaced')"
```

**Checkpoint**

- [ ] You can predict the output of each command before you run it, using the table in Part 1.

### Step 8: Multi-stage build

Goal: install with a full toolchain, and ship without it.

Copy the multi-stage solution into your folder, read it, and build it:

```bash
cp ../solution/Dockerfile.multistage .
cat Dockerfile.multistage
time docker build -f Dockerfile.multistage -t dockerlab:multi .
docker images dockerlab
```

The important lines:

```dockerfile
FROM python:3.12 AS builder                       # stage 1: the full image, with compilers
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim                             # stage 2: a clean, small image
COPY --from=builder /install /usr/local           # only the installed packages come along
...                                               # the rest is the same as Step 6
```

| Line | Meaning |
| --- | --- |
| `AS builder` | Names the stage, so later stages can refer to it. |
| `--prefix=/install` | pip installs into `/install` instead of the system folders, so the result is easy to copy as one folder. |
| `COPY --from=builder /install /usr/local` | Copies from the builder stage instead of from the build context. `/usr/local` is where the slim image's Python looks for packages. |

Run it and confirm it behaves exactly like Step 6:

```bash
docker run -d --name multi -p 8080:8000 dockerlab:multi
curl localhost:8080
docker ps
docker rm -f multi
```

**Checkpoint**

- [ ] The final image is about the size of `v6`, although the builder stage used the ~1 GB image. None of the builder's tools are in the result.
- [ ] You can explain why the saving here is small: Flask and gunicorn are pure Python, so they need no compiler. With packages that compile C code (for example `psycopg2` built from source), single-stage needs `gcc` and headers in the final image, and multi-stage leaves them behind.

### Step 9: Results table

Fill in your numbers:

| Image | Base | Size | Rebuild after a code change | Runs as | Secret in image |
| --- | --- | --- | --- | --- | --- |
| `v1` (bad) | `python:3.12` | | | root | yes |
| `v2` (slim, ordered) | `python:3.12-slim` | | | root | yes |
| `v6` (single-stage final) | `python:3.12-slim` | | | appuser | no |
| `multi` (multi-stage final) | builder `python:3.12`, runtime `python:3.12-slim` | | | appuser | no |

For reference, on one Apple Silicon laptop: `v1` was 1.63 GB with a 7-second rebuild (pip ran again), `v2` and `v6` were 226 MB with a rebuild under 1 second, and `multi` was 213 MB. Your numbers differ by machine and CPU type.

### Stretch goals

- **Distroless:** change the runtime stage of the multi-stage build to a distroless Python image. What breaks? (There is no shell, so `RUN useradd` fails: use the image's built-in non-root user instead. Its Python version can also differ from the builder's, and installed packages must match the Python that runs them.)
- **Build secrets:** read about `RUN --mount=type=secret`, which gives a build step a secret without storing it in any layer.
- **Compose:** write a `compose.yaml` that runs this image with the `lab6-data` volume and the port mapping, so `docker compose up` replaces the long `docker run` command.
- **Push it:** tag `dockerlab:multi` with your ECR repository name and push it, as in Lab 5, Step 2.

### Troubleshooting

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker is not running | Start Docker Desktop. In CloudShell, open a new tab. |
| `port is already allocated` | Another container uses port 8080 | `docker ps`, then `docker rm -f <name>`, or use `-p 8082:8000`. |
| `Conflict. The container name "/v5" is already in use` | A container from an earlier try still exists | `docker rm -f v5` |
| `curl: (7) Failed to connect` | Missing `-p`, wrong port, or the app has not started yet | `docker ps` shows the port mapping. Wait a second, then check `docker logs <name>`. |
| `curl: (52) Empty reply from server` | The app listens on `127.0.0.1` inside the container | The bind address must be `0.0.0.0`. |
| `/visits` returns 500 | `/data` is not writable by `appuser` | Step 5 Part B: `mkdir` and `chown` before `VOLUME` and `USER`. |
| Container exits at once | The `CMD` failed | `docker logs <name>`, for example a typo in `app:app`. |
| `no space left on device` | CloudShell has limited disk, and `python:3.12` is large | `docker rmi dockerlab:v1 python:3.12`, then rebuild. |
| `pip install` runs on every build | `COPY . .` is above `RUN pip install` | Copy `requirements.txt` first, as in Step 2. |
| `sed: 1: "Dockerfile": ...` on a Mac | macOS `sed -i` needs an empty argument | Use `sed -i ''` instead of `sed -i`, or edit the file in an editor. |

### Discussion (10 minutes)

- Which change saved the most size? Which saved the most time? Which mattered most for security?
- The `.env` file was in `v1` and `v2`. If those images had been pushed to a public registry, what would you have to do? (Rotate the password. Deleting the image does not un-leak it.)
- Why does `ARG APP_VERSION` sit near the bottom, and `RUN useradd` near the top?
- Lab 5 sets environment variables in the ECS task definition. Which line of this Dockerfile provides the default that the task definition overrides?

### Cleanup

Everything in this lab is local, so there is no AWS cost. Free the disk space:

```bash
docker rm -f v1 v2 v5 v6 multi sick a b 2>/dev/null
docker rmi dockerlab:v1 dockerlab:v2 dockerlab:v3 dockerlab:1.0 dockerlab:1.1 \
           dockerlab:v5 dockerlab:v6 dockerlab:multi greet
docker volume rm lab6-data
docker images
```

- [ ] No `dockerlab` containers in `docker ps -a`.
- [ ] The `lab6-data` volume is deleted.

### What to submit

One PDF with:

1. Your final `Dockerfile` and `.dockerignore`.
2. The completed results table from Step 9.
3. Screenshots of: `docker exec v1 cat /.env` printing the password, `ls -a /app` without it in Step 3, the 500 and its log line in Step 5 Part A, the visit counter at 3 in Step 5 Part B, and `docker ps` with one `healthy` and one `unhealthy` container in Step 6.
4. Answers to the four questions in Part 1 and the discussion questions.
