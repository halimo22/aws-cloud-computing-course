# Lab 6 assignment: a three-tier app with Docker, Compose, ECR and ECS

## Overview

You get the code of a small notes app with three parts: a web page, an API, and a database. You write every Dockerfile and the Compose file yourself. You build the API image twice (single-stage and multi-stage) and compare them, connect the three containers by hand with a Docker network, replace those commands with one Compose file, and finally push the images to Amazon ECR and run the app on Amazon ECS, with the database on Amazon RDS.

The app never changes. Only its **connection string** changes between your machine and AWS, and that is the main idea of the assignment: build an image once, configure it differently in each place.

**What you build**

```
On your machine (Parts 2 to 6)

  browser --:8080--> frontend ---/api/---> backend ---5432---> db
                     nginx                 Flask (Python)      PostgreSQL 16
                     network: front        front + back        network: back (internal)

On AWS (Part 7)

  browser --:80--> ECS Fargate task, one public IP             Amazon RDS for PostgreSQL
                   frontend --localhost:8000--> backend ---5432---> (security group: 5432 from the task only)
                   both images pulled from Amazon ECR
```

**By the end you can:**

1. Write a single-stage and a multi-stage Dockerfile, and explain the size difference.
2. Separate build-time dependencies (a compiler, header files) from run-time ones (a shared library).
3. Explain what a Docker network does, connect containers by name, and isolate them on separate networks.
4. Write a database connection string, and choose its host depending on where the app and the database run.
5. Describe a multi-container app in one `compose.yaml` with networks, volumes, health checks and start-up order.
6. Push images to ECR, and run two containers in one ECS task that talks to RDS.

**Before you start**

- Finish [Lab 6](../README.md) (Dockerfile instructions) and [Lab 5](../../lab-05-containers-ecr-ecs/) (ECR and ECS). This assignment assumes both.
- A place to run Docker with Compose v2. **AWS CloudShell** is recommended: it has Docker, Git and the AWS CLI, and it runs on x86_64, like a default Fargate task. Docker Desktop on a laptop also works.
- Check Compose:

```bash
docker compose version
```

If CloudShell answers `'compose' is not a docker command`, install the plugin for your user (about 60 MB):

```bash
mkdir -p ~/.docker/cli-plugins
curl -sSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m)" \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

- Get the starter code:

```bash
git clone https://github.com/halimo22/aws-cloud-computing-course.git
cd aws-cloud-computing-course/lab-06-docker-dockerfile/assignment
```

Run every command in this assignment from this `assignment` folder unless a step says otherwise.

**Naming rule:** prefix every AWS resource with `lab6-<yourname>` (for example `lab6-sara-db`).

**Cost warning:** Part 7 creates an RDS database and a Fargate task. Both are cheap (RDS `db.t4g.micro` is free-tier eligible on eligible accounts; the task costs about 1 cent per hour), but do the Part 7 cleanup the same day.

### The starter code

| File | What it is | Do you change it? |
| --- | --- | --- |
| `backend/app.py` | The API (Flask, served by gunicorn on port 8000). | No |
| `backend/requirements.txt` | Its three dependencies. `psycopg2` is the PostgreSQL driver, compiled from C source when installed. | No |
| `frontend/index.html` | The web page. It calls `/api/...` on the same server it came from. | No |
| `frontend/default.conf.template` | nginx config: serve the page, forward `/api/` to `${BACKEND_URL}`. | No |

The API reads **one** setting, the environment variable `DATABASE_URL`, and nothing else:

| Endpoint | Returns | Touches the database |
| --- | --- | --- |
| `GET /api/health` | `{"status": "ok"}`. Used by the health check. | No |
| `GET /api/info` | The container's hostname, the parts of `DATABASE_URL` (never the password), and either `db_version` or `db_error`. Your main debugging tool. | Yes, but never fails: it reports the error instead |
| `GET /api/messages` | The last 50 messages. Creates the table on first use. | Yes |
| `POST /api/messages` | Adds `{"text": "..."}` (1 to 500 characters). | Yes |

### What you write

| File | Part |
| --- | --- |
| `backend/Dockerfile.single` | 2 |
| `backend/.dockerignore` | 2 |
| `backend/Dockerfile` (multi-stage) | 3 |
| `frontend/Dockerfile` | 4 |
| `compose.yaml` and `.env.example` (and a `.env` you never submit) | 6 |
| An ECS task definition (JSON) | 7 |

---

## Part 1: Concepts

Read this part before you start. Part 8 asks questions about it.

### 1.1 Docker networks

**The problem.** Every container gets its own network stack: its own IP address, its own ports, and its own `localhost`. Inside the backend container, `localhost` means *the backend container*, never your laptop and never the database container. Containers reach each other only through a **network** they share.

**Network drivers**

| Driver | What it gives | Typical use |
| --- | --- | --- |
| `bridge` (the default network called `bridge`) | A private network on one host. Containers get an IP but **no name lookup**. | `docker run` with no `--network`. Fine for one container. |
| `bridge` (a network you create) | The same, plus a **built-in DNS server**: containers find each other by name. | Every multi-container app on one host. Compose creates these for you. |
| `host` | No isolation: the container uses the host's network directly. `-p` is ignored. | Rare. Performance tests, some monitoring tools. |
| `none` | No network at all, only `localhost`. | Batch jobs that must not talk to anything. |
| `overlay` | One network spread over several hosts. | Docker Swarm. On AWS, ECS and VPCs do this job instead. |

**Default bridge vs a network you create**

| | Default `bridge` | User-defined bridge (`docker network create`) |
| --- | --- | --- |
| Find another container by name | No, only by IP, which changes on every restart | Yes: `db`, `backend` |
| Isolation | Every container without `--network` lands here together | Only the containers you attach |
| Attach or detach a running container | No | Yes: `docker network connect` / `disconnect` |
| Recommended | No | Yes |

**Two kinds of traffic, two different rules**

| Traffic | What it needs | Example |
| --- | --- | --- |
| From outside (your browser, `curl` on the host) into a container | A **published** port: `-p host:container`, or `ports:` in Compose | `-p 8080:80`: host port 8080 goes to container port 80 |
| From one container to another on the same network | **Nothing.** Use the other container's **name** and its **container** port | `db:5432`, `http://backend:8000` |

`EXPOSE` in a Dockerfile (and `expose:` in Compose) only documents a port. It does not publish it, and containers on the same network can reach every port anyway.

**What networks are used for**

| Use | How | The same idea on AWS (Labs 3 and 4) |
| --- | --- | --- |
| **Service discovery**: find a service by a stable name, not an IP | Containers on a user-defined network resolve each other's names | Cloud Map, ECS Service Connect, an RDS endpoint name |
| **Segmentation**: split tiers so a hacked web server cannot reach the database | Put each tier on its own network; only the backend joins both | Public and private subnets |
| **Least exposure**: publish only the entry point | Only the frontend has `-p`; the database has none | A security group that allows 5432 only from the app's security group |
| **No internet for the data tier** | A network created with `internal: true` has no route out | A private subnet with no NAT gateway |

**Commands**

| Command | Does |
| --- | --- |
| `docker network ls` | List networks. |
| `docker network create notes-net` | Create a user-defined bridge network. |
| `docker run --network notes-net ...` | Start a container on that network. |
| `docker network connect notes-net web` | Attach a running container to another network. |
| `docker network inspect notes-net` | Show its subnet and the containers attached, with their IPs. |
| `docker network rm notes-net` | Delete it (no containers may be attached). |

### 1.2 Connection strings

A **connection string** packs everything a program needs to reach a database into one value. This app uses the URL form that PostgreSQL drivers understand:

```
postgresql://notes:s3cret123@db:5432/notes?sslmode=require
|          |  |    | |      | |  | |  | |   | |            |
+- scheme -+  user   password host port  db    options
```

| Part | Example | Meaning |
| --- | --- | --- |
| scheme | `postgresql://` | Which kind of database (`mysql://`, `mongodb://`, `redis://` for others). |
| user | `notes` | The database user, **not** a Linux user. |
| password | `s3cret123` | That user's password. |
| host | `db` | Where the database is, **as seen from the app**. The part that changes most. |
| port | `5432` | PostgreSQL's port, **inside** the database container (not a published host port). |
| database | `notes` | One server holds many databases; this picks one. |
| options | `?sslmode=require` | Extra settings, such as encryption or a timeout. |

**The host depends on where the app runs**, not on where you are sitting:

| The app runs | The database runs | Host in the connection string |
| --- | --- | --- |
| On your laptop, not in Docker | In a container started with `-p 5432:5432` | `localhost` |
| In a container | In a container on the **same user-defined network** | The container's name or Compose service name: `db` |
| In a container | On your laptop (Docker Desktop) | `host.docker.internal` |
| In an ECS task | Amazon RDS | The RDS endpoint, for example `lab6-sara-db.abc123.us-east-1.rds.amazonaws.com` |
| In a container | In a container on the default `bridge`, or on another network | **Nothing works.** There is no name to use, and no route. |

**Rules for connection strings**

- **Special characters must be URL-encoded.** In a password, `@` ends the user part, `:` splits user and password, `/` starts the database name, and `?` or `#` start the options. Encode them: `p@ss:w/rd` becomes `p%40ss%3Aw%2Frd`. Easiest: use letters and digits only. To encode one: `python3 -c "from urllib.parse import quote; print(quote('p@ss:w/rd', safe=''))"`.
- **Never bake one into an image.** Not in `ENV`, not in `ARG`, not in a copied `.env` file. Anyone who can pull the image can read it (Lab 6, Step 3). Give it at **run time**: `docker run -e`, Compose `environment:` filled from a `.env` file that is never committed, or the ECS task definition (better: its `secrets` field with Secrets Manager).
- **One variable, every environment.** The image reads `DATABASE_URL`. To move from your laptop to AWS you change that value, not the image.

### 1.3 Docker Compose

**What it is.** A tool that reads one YAML file, `compose.yaml`, describing a whole multi-container app: its **services** (containers), **networks** and **volumes**. `docker compose up` builds the images, creates the networks and volumes, and starts the containers in the right order. `docker compose down` removes them again.

**What it is used for**

- **Replacing long `docker run` commands** with one file you keep in Git. Part 5 takes about ten commands; Part 6 takes one.
- **Identical development environments**: a new team member runs `git clone` and `docker compose up`, and gets the same database version, the same settings, and the same network as everyone else.
- **Test environments in CI**: start the app and its database, run the tests, throw everything away.
- **Demos and small single-server deployments.**

**What it is not for:** running across several servers, autoscaling, or rolling updates without downtime. That is the job of an orchestrator such as Amazon ECS or Kubernetes. The ECS task definition in Part 7 is AWS's version of the same idea: a list of containers with their images, settings and dependencies.

**What Compose does for you**

- The **project name** is the folder name (here `assignment`). Every container, network and volume is prefixed with it: container `assignment-backend-1`, network `assignment_back`, volume `assignment_db-data`.
- If you define no networks, Compose creates one called `<project>_default` and attaches every service. **The service name is the DNS name**: a service called `db` is reachable as `db`.
- It reads `.env` in the same folder and fills in every `${VARIABLE}` in `compose.yaml`. Write `$$` for a literal `$` that the container should see.

**From `docker run` to `compose.yaml`**

| `docker run` option | `compose.yaml` |
| --- | --- |
| `--name backend` | The service name: `services: backend:` |
| `docker build -t notes-backend:multi backend` | `build: ./backend` and `image: notes-backend:multi` |
| `-p 8080:80` | `ports: ["8080:80"]` |
| `-e KEY=value` | `environment: { KEY: value }` |
| `-v notes-data:/var/lib/postgresql/data` | `volumes:` on the service, and the volume under the top-level `volumes:` |
| `--network notes-net` | `networks:` on the service, and the network under the top-level `networks:` |
| `--restart unless-stopped` | `restart: unless-stopped` |
| `--health-cmd ...` | `healthcheck:` (or the image's own `HEALTHCHECK`) |
| *(start db first, wait, then the backend)* | `depends_on: { db: { condition: service_healthy } }` |

**`depends_on`, short and long form.** `depends_on: [db]` only means *create db first*. PostgreSQL then needs a few seconds before it accepts connections. `condition: service_healthy` waits until the `db` health check passes, so the backend's first request does not fail.

**Commands**

| Command | Does |
| --- | --- |
| `docker compose config` | Print the file with every `${VARIABLE}` filled in. Run it first: it catches YAML and variable mistakes. |
| `docker compose up -d --build` | Build the images, create everything, start in the background. |
| `docker compose ps` | List this project's containers, with health and ports. |
| `docker compose logs -f backend` | Follow one service's logs. |
| `docker compose exec backend sh` | Open a shell in a running service. |
| `docker compose restart backend` | Restart one service. |
| `docker compose down` | Stop and delete containers and networks. **Volumes are kept.** |
| `docker compose down -v` | The same, and delete the volumes: **the data is gone**. |

---

## Part 2: Backend image, single-stage

**Write `backend/Dockerfile.single` and `backend/.dockerignore`.** Requirements:

1. Base image `python:3.12-slim`.
2. Install the Debian packages that `psycopg2` needs to compile (Task 2.1 finds them).
3. Create a non-root user and run the app as that user.
4. `WORKDIR /app`. Copy `requirements.txt` and install it **before** copying `app.py`, so a code change does not re-run `pip install`.
5. `.dockerignore` keeps out at least `.env`, `__pycache__/` and the Dockerfiles.
6. `EXPOSE 8000`, a `HEALTHCHECK` that calls `http://localhost:8000/api/health` (the slim image has no `curl`: use Python, as in Lab 6 Step 6), and a `CMD` in exec form that runs `gunicorn --bind 0.0.0.0:8000 app:app`.
7. **No `DATABASE_URL`** anywhere in the Dockerfile.

**Task 2.1: find the build dependencies.** Start with no `apt-get` line at all and build:

```bash
docker build -f backend/Dockerfile.single -t notes-backend:single backend
```

The last argument, `backend`, is the **build context**: the folder whose files `COPY` can see. `-f` names the Dockerfile.

`pip install` fails. Read the error: `pg_config executable not found`. `pg_config` comes with the PostgreSQL client headers. Add this before the `pip install` step and build again:

```dockerfile
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
 && rm -rf /var/lib/apt/lists/*
```

| Package | Why psycopg2 needs it |
| --- | --- |
| `gcc` | The C compiler. psycopg2 is partly written in C. |
| `libc6-dev` | The standard C header files (`stdio.h` and friends). Without it, `gcc` fails at once. |
| `libpq-dev` | PostgreSQL's client library, its headers, and `pg_config`, which tells the compiler where they are. |

**Screenshot A1:** the `pg_config executable not found` error.

**Task 2.2: run the backend on its own.**

```bash
docker images notes-backend
docker run -d --name api-alone -p 8000:8000 notes-backend:single
curl localhost:8000/api/health
curl localhost:8000/api/info
curl -i localhost:8000/api/messages
docker run --rm notes-backend:single gcc --version
docker rm -f api-alone
```

`/api/health` works, `/api/info` reports `"db_error": "DATABASE_URL is not set"`, and `/api/messages` returns `503`. The web server runs; there is just no database yet. And the compiler, used once during the build, is still in the image.

**Screenshot A2:** `docker images notes-backend` with the size, the three `curl` outputs, and `gcc --version` printing a version.

---

## Part 3: Backend image, multi-stage

**Write `backend/Dockerfile`** (no suffix: this becomes the image you use from now on). Requirements:

1. A first stage named `builder`, from `python:3.12-slim`, that installs `gcc libc6-dev libpq-dev` and runs `pip install --no-cache-dir --prefix=/install -r requirements.txt`.
2. A second stage, from a fresh `python:3.12-slim`, that installs only `libpq5` (the PostgreSQL client **library**, without headers) and copies the packages: `COPY --from=builder /install /usr/local`.
3. Requirements 3, 4, 6 and 7 from Part 2 still apply to the final stage.

```bash
docker build -t notes-backend:multi backend
docker images notes-backend
docker run --rm notes-backend:multi gcc --version
docker run --rm notes-backend:multi whoami
docker history notes-backend:multi
```

`gcc --version` now fails with `executable file not found`: the compiler stayed in the builder stage.

If the container starts and crashes with `ImportError: libpq.so.5: cannot open shared object file`, you forgot `libpq5`. The compiled psycopg2 needs the library at run time, even though it no longer needs the compiler. **Build-time and run-time dependencies are different lists.**

**Fill in:**

| Image | Size | `gcc` in the image | Runs as |
| --- | --- | --- | --- |
| `notes-backend:single` | | | |
| `notes-backend:multi` | | | |

For reference, on one Apple Silicon laptop: single-stage 517 MB, multi-stage 221 MB.

**Screenshot A3:** `docker images notes-backend` showing both tags and sizes, and `gcc --version` failing in `notes-backend:multi`.

---

## Part 4: Frontend image

**Write `frontend/Dockerfile`.** Requirements:

1. Base image `nginx:1.27-alpine`.
2. `ENV BACKEND_URL=http://backend:8000` as the default.
3. Copy `default.conf.template` to `/etc/nginx/templates/`. At start-up the nginx image fills in `${BACKEND_URL}` and writes the result to `/etc/nginx/conf.d/default.conf`.
4. Copy `index.html` to `/usr/share/nginx/html/`.
5. `EXPOSE 80`. You need no `CMD`: the nginx image already has one, and your image inherits it.

There is nothing to compile, so a single stage is right here. (A frontend built with React or Vue would use a multi-stage build: stage 1 runs `npm run build` in a Node image, stage 2 copies only the built files into nginx.)

```bash
docker build -t notes-frontend:1.0 frontend
docker run -d --name web-alone -p 8080:80 notes-frontend:1.0
docker ps -a --filter name=web-alone
docker logs web-alone
docker rm -f web-alone
```

The container **exits** at once. The log says:

```
nginx: [emerg] host not found in upstream "backend" in /etc/nginx/conf.d/default.conf:16
```

nginx looks up `backend` when it starts. On the default `bridge` network there is no name lookup, and there is no container called `backend` anyway. Part 5 fixes both.

**Screenshot A4:** the `Exited (1)` status and the `host not found in upstream` log line.

---

## Part 5: Connect the containers by hand with a Docker network

Here you do with plain `docker` commands what Compose will do for you in Part 6, so you see every piece.

**5.1 Create a network and a volume**

```bash
docker network create notes-net
docker volume create notes-data
```

**5.2 Start the database.** The official `postgres` image creates the user, password and database from these three variables the first time it starts with an empty volume. It needs no Dockerfile, and no `-p`: nothing outside the network may reach it.

```bash
docker run -d --name db --network notes-net \
  -e POSTGRES_USER=notes \
  -e POSTGRES_PASSWORD=<choose-a-password> \
  -e POSTGRES_DB=notes \
  -v notes-data:/var/lib/postgresql/data \
  postgres:16-alpine
docker logs db 2>&1 | tail -2    # wait for "database system is ready to accept connections"
```

**5.3 Start the backend with your connection string.** Write `DATABASE_URL` yourself from the values in 5.2, using Part 1.2. The container's name, `backend`, is the name nginx looks for.

```bash
docker run -d --name backend --network notes-net \
  -e DATABASE_URL='<your connection string>' \
  notes-backend:multi
```

**5.4 Start the frontend.** It is the only container with a published port.

```bash
docker run -d --name frontend --network notes-net -p 8080:80 notes-frontend:1.0
docker ps
```

**5.5 Use the app**

```bash
curl localhost:8080/api/info
curl -X POST localhost:8080/api/messages -H 'Content-Type: application/json' -d '{"text": "hello from a Docker network"}'
curl localhost:8080/api/messages
```

On a laptop, also open `http://localhost:8080` and add a message from the page.

`/api/info` now shows `db_host: "db"` and a `db_version` starting with `PostgreSQL 16`. The request went browser -> frontend (published port) -> backend (by name, port 8000) -> db (by name, port 5432).

**Screenshot A5:** `docker ps` (only the frontend has a port mapping) and the `/api/info` output with `db_version`.

**5.6 See the DNS and the isolation**

```bash
docker exec backend getent hosts db                     # db's IP, from Docker's DNS
docker network inspect notes-net --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
docker run --rm alpine ping -c 1 db                     # default bridge: "bad address 'db'"
docker run --rm --network notes-net alpine ping -c 1 db # same network: replies
```

**Screenshot A6:** the four outputs.

**5.7 Break the connection string on purpose.** Start a second backend with a wrong `DATABASE_URL`, call it, and remove it. Repeat for each row, changing one part at a time:

```bash
docker run -d --name api-test --network notes-net -p 8001:8000 \
  -e DATABASE_URL='<the broken connection string>' notes-backend:multi
sleep 2; curl localhost:8001/api/info; docker rm -f api-test
```

| What you change | Your `db_error` (copy the key words) | Why, in one sentence |
| --- | --- | --- |
| host `db` -> `localhost` | | |
| host `db` -> `database` | | |
| port `5432` -> `8080` | | |
| a wrong password | | |
| database `notes` -> `shop` | | |

**Screenshot A7:** two of the five errors.

**5.8 Clean up** (keep the images, Part 6 uses them):

```bash
docker rm -f frontend backend db
docker network rm notes-net
docker volume rm notes-data
```

---

## Part 6: Docker Compose

**Write `compose.yaml`** in the `assignment` folder (next to `backend/` and `frontend/`), **`.env.example`**, and a **`.env`** with your real values. Requirements:

1. Three services named `db`, `backend` and `frontend`.
   - `db` uses the image `postgres:16-alpine`.
   - `backend` is **built** from `./backend` with your multi-stage Dockerfile and tagged `notes-backend:multi`.
   - `frontend` is **built** from `./frontend` and tagged `notes-frontend:1.0`.
2. **Two networks**: `front` and `back`. `back` is `internal: true`. `db` is only on `back`, `frontend` is only on `front`, and `backend` is on both.
3. **Only `frontend` publishes a port**: `8080:80`.
4. The database user, password and database name come from `.env` as `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`. The backend's **`DATABASE_URL` is built from the same three variables**, so the password is written in one place only.
5. A named volume for `/var/lib/postgresql/data`.
6. A `healthcheck` on `db` that runs `pg_isready -U <user> -d <database>`. The backend waits for `db` to be **healthy**, and the frontend waits for the backend to be **healthy** (the backend's health check comes from its Dockerfile).
7. `restart: unless-stopped` on all three.
8. `.env.example` has the same keys as `.env` with a placeholder password. `.env` is never submitted or committed.

**Run it**

```bash
docker compose config        # check DATABASE_URL: is the host db, and is the password filled in?
docker compose up -d --build
docker compose ps            # wait until all three say (healthy) or Up
```

**Screenshot A8:** `docker compose ps` with all three services running and healthy, and the ports column showing a port only on the frontend.

**Use it**

```bash
curl localhost:8080/api/info
curl -X POST localhost:8080/api/messages -H 'Content-Type: application/json' -d '{"text": "hello from Compose"}'
curl -X POST localhost:8080/api/messages -H 'Content-Type: application/json' -d '{"text": "second message"}'
curl localhost:8080/api/messages
docker compose logs backend --tail 5
```

**Screenshot A9:** the messages list (on a laptop, the browser page instead) and the backend's log lines for the two `POST` requests.

**Prove the network design**

```bash
docker network ls --filter name=assignment
docker network inspect assignment_back --format '{{range .Containers}}{{.Name}} {{end}}'
docker network inspect assignment_front --format '{{range .Containers}}{{.Name}} {{end}}'
docker compose exec backend getent hosts db      # works: backend is on back
docker compose exec frontend ping -c 1 db        # fails: frontend is not on back
docker compose exec db ping -c 1 -W 2 1.1.1.1    # fails: back is internal, no internet
```

If your folder has another name, replace `assignment` with it: `docker compose ls` shows the project name.

**Screenshot A10:** all six outputs.

**Prove the data is in the volume**

```bash
docker compose down              # containers and networks deleted
docker compose up -d
sleep 10; curl localhost:8080/api/messages   # your messages are still there
docker compose down -v           # this time the volume goes too
docker compose up -d
sleep 10; curl localhost:8080/api/messages   # []
```

**Screenshot A11:** the messages after `down` / `up`, then `[]` after `down -v` / `up`.

---

## Part 7: Push to Amazon ECR and run on Amazon ECS with RDS

On AWS the three services change form:

| Locally (Compose) | On AWS | What changes in the configuration |
| --- | --- | --- |
| `db` container, volume `db-data` | **Amazon RDS** for PostgreSQL: AWS runs, patches and backs up the database | The host in `DATABASE_URL` becomes the RDS endpoint |
| `backend` and `frontend` containers | Two containers in **one ECS task** | `BACKEND_URL` becomes `http://localhost:8000` (see 7.6) |
| Networks `front` and `back` | The VPC and **security groups** | `5432` is allowed only from the task's security group |
| `.env` | The task definition (better: Secrets Manager) | |
| `docker compose up` | An ECS **service** | |

The images do not change.

### 7.1 Check the image architecture

```bash
docker image inspect notes-backend:multi --format '{{.Os}}/{{.Architecture}}'
```

`linux/amd64` (CloudShell, Intel laptops): use `X86_64` in the task definition. `linux/arm64` (Apple Silicon laptops): use `ARM64`. A mismatch makes the task stop with `exec format error`.

### 7.2 Push both images to ECR

In CloudShell (or a terminal where the AWS CLI works), in region `us-east-1`:

```bash
PREFIX=lab6-<yourname>
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

aws ecr create-repository --repository-name $PREFIX/backend  --region us-east-1
aws ecr create-repository --repository-name $PREFIX/frontend --region us-east-1

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin $REGISTRY

docker tag notes-backend:multi $REGISTRY/$PREFIX/backend:1.0
docker tag notes-frontend:1.0  $REGISTRY/$PREFIX/frontend:1.0
docker push $REGISTRY/$PREFIX/backend:1.0
docker push $REGISTRY/$PREFIX/frontend:1.0

aws ecr describe-images --repository-name $PREFIX/backend \
  --query 'imageDetails[].[imageTags[0],imageSizeInBytes]' --output table
```

ECR reports the **compressed** size, so it is smaller than `docker images`. (Compose can do the tag and push for you: set `image:` to the ECR name and run `docker compose push`.)

**Screenshot A12:** both `docker push` outputs and the `describe-images` table.

### 7.3 A security group for the task

**EC2 > Security Groups > Create security group** `lab6-<yourname>-app-sg` in the **default VPC**, with one inbound rule: **HTTP (80) from My IP**. Port 8000 is not opened: the backend is reached only by the frontend, inside the task.

### 7.4 The database: Amazon RDS for PostgreSQL

**RDS > Databases > Create database**, with **Standard create** (full configuration):

| Setting | Value | Why |
| --- | --- | --- |
| Engine | PostgreSQL, version 16.x | The same major version as `postgres:16-alpine`. |
| Template | Free tier (or Dev/Test if Free tier is not offered) | Cheapest. |
| Deployment | Single-AZ, no standby | A standby doubles the cost. |
| DB instance identifier | `lab6-<yourname>-db` | Part of the endpoint name. |
| Master username | `notes` | The *user* part of the connection string. |
| Credentials | Self managed, a password of **letters and digits only** | The *password* part. RDS rejects `@`, `/` and `"` anyway, and other symbols would need URL-encoding. |
| Instance class | `db.t4g.micro` (or `db.t3.micro`) | Free-tier size. |
| Storage | gp3, 20 GiB, storage autoscaling off | Minimum. |
| Compute resource | Don't connect to an EC2 compute resource | |
| VPC | Default VPC | Same VPC as the task. |
| Public access | **No** | Only resources inside the VPC can reach it. |
| VPC security group | Create new: `lab6-<yourname>-db-sg` | Fixed in 7.5. |
| Additional configuration > **Initial database name** | `notes` | The *database* part. **If you skip it, RDS creates no `notes` database**, and the app reports `database "notes" does not exist`. |
| Backup retention | 0 or 1 day | Faster to create and delete. |
| Performance Insights, Enhanced monitoring | Off | Not needed, and not free. |

Creation takes 5 to 10 minutes. When the status is **Available**, copy the **Endpoint** from the **Connectivity & security** tab.

**Screenshot A13:** the database's Connectivity & security tab showing the endpoint, port 5432, and *Publicly accessible: No*.

### 7.5 Let only the task reach the database

Open `lab6-<yourname>-db-sg`, **Edit inbound rules**: delete the rule RDS added for your IP, and add **PostgreSQL (5432)** with **source: `lab6-<yourname>-app-sg`**. This rule is the AWS version of the `back` network: only members of the app security group can reach the database.

**Screenshot A14:** db-sg's inbound rules.

### 7.6 The task definition

Create the log group first (the task's execution role can write to a log group but not create one):

```bash
aws logs create-log-group --log-group-name /ecs/lab6-<yourname>-notes --region us-east-1
```

**ECS > Task definitions > Create new task definition > Create new task definition with JSON.** Paste this and replace every `<...>`:

```json
{
  "family": "lab6-<yourname>-notes",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "256",
  "memory": "512",
  "runtimePlatform": { "operatingSystemFamily": "LINUX", "cpuArchitecture": "X86_64" },
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/lab6-<yourname>/backend:1.0",
      "essential": true,
      "environment": [
        { "name": "DATABASE_URL", "value": "postgresql://notes:<password>@<rds-endpoint>:5432/notes?sslmode=require" }
      ],
      "healthCheck": {
        "command": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=2)"],
        "interval": 10, "timeout": 3, "retries": 3, "startPeriod": 10
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/lab6-<yourname>-notes",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "backend"
        }
      }
    },
    {
      "name": "frontend",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/lab6-<yourname>/frontend:1.0",
      "essential": true,
      "portMappings": [{ "containerPort": 80, "protocol": "tcp" }],
      "environment": [
        { "name": "BACKEND_URL", "value": "http://localhost:8000" }
      ],
      "dependsOn": [{ "containerName": "backend", "condition": "HEALTHY" }],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/lab6-<yourname>-notes",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "frontend"
        }
      }
    }
  ]
}
```

What is different from Compose, and why:

| Line | Meaning |
| --- | --- |
| `"networkMode": "awsvpc"` | The whole **task** gets one network interface and one IP. All its containers share it, like processes on one machine. |
| `BACKEND_URL` = `http://localhost:8000` | Because they share the network, the frontend reaches the backend on `localhost`. There is no Docker DNS and no name `backend` here. Same image, different setting. |
| `DATABASE_URL` host = the RDS endpoint | The database is no longer a container. `?sslmode=require` encrypts the connection; RDS for PostgreSQL 15 and later requires SSL by default. |
| `healthCheck` on the backend | **ECS ignores the `HEALTHCHECK` in the image.** A container health check must be written in the task definition. |
| `dependsOn` ... `HEALTHY` | The same as Compose's `condition: service_healthy`. |
| No `portMappings` on the backend | Traffic between containers of one task needs none. Only port 80 is opened, and only by the security group. |
| `essential: true` on both | If either container stops, ECS stops the task and the service starts a new one. |

The `DATABASE_URL` here is plain text: anyone who can read the task definition can read the password. For this assignment that is accepted; the stretch goals move it into Secrets Manager.

**Screenshot A15:** the task definition revision's JSON tab showing both containers' `environment` (two screenshots are fine).

### 7.7 Cluster and service

1. **ECS > Clusters > Create cluster** `lab6-<yourname>-cluster`, infrastructure **AWS Fargate** only.
2. In the cluster, **Services > Create**: launch type **Fargate**, task definition `lab6-<yourname>-notes` (latest revision), service name `lab6-<yourname>-notes`, desired tasks **1**.
3. Networking: **default VPC**, its public subnets, security group **`lab6-<yourname>-app-sg`** only (remove the default one), **Public IP: turned on** (the task pulls from ECR over the internet). Load balancing: none.
4. Wait for *1/1 tasks running*. Open the task: both containers should show **Running**, and the backend **Healthy**.
5. Copy the task's **Public IP** and open `http://<public-ip>/`. Add two messages.

**Screenshot A16:** the task page with both containers running and the backend healthy.

**Screenshot A17:** the browser at the public IP, with the Connection box showing `db_host` = your RDS endpoint and a `db_version`, and your two messages.

**Screenshot A18:** the log group `/ecs/lab6-<yourname>-notes` with a `backend/...` stream showing your requests.

### 7.8 Break it with a security group

Delete the `5432` rule from `lab6-<yourname>-db-sg` and reload the page. After 3 seconds, `/api/info` reports `timeout expired`: the packets are dropped, exactly like a container on the wrong Docker network. Add the rule back and reload: it works again, with no restart.

**Screenshot A19:** the `timeout expired` error.

### 7.9 Clean up AWS (same day)

1. **ECS:** update the service to 0 desired tasks, delete the service, then the cluster. Optionally deregister the task definition.
2. **RDS:** select the database, **Actions > Delete**, untick *Create final snapshot*, untick *Retain automated backups*, confirm.
3. **ECR:** delete both repositories (tick *force*).
4. **CloudWatch Logs:** delete `/ecs/lab6-<yourname>-notes`.
5. **EC2 > Security Groups:** delete `db-sg` first (it refers to `app-sg`), then `app-sg`. They can be deleted only after the database and the task are gone.

**Screenshot A20:** the ECS clusters, RDS databases and ECR repositories lists with none of your `lab6-<yourname>` resources.

---

## Part 8: Written questions

Answer each in two to four sentences.

1. Inside the backend container, why does a connection string with `localhost` fail, while `db` works?
2. In Part 4, the frontend container exited at once. In Part 5 the same image worked. What changed? Name two things.
3. What does a user-defined network give you that the default `bridge` network does not?
4. The database has no `ports:` in your Compose file. How does the backend reach it anyway? What could go wrong if you added `"5432:5432"`?
5. What can the `db` container no longer do because `back` is `internal: true`? Why is that a good thing? Which AWS feature from Lab 3 does the same job?
6. What is the difference between `depends_on: [db]` and `depends_on` with `condition: service_healthy`? What would happen to the first request without the condition?
7. Why is the single-stage image so much larger than the multi-stage one? Name what is in it that the app never uses. Why must the multi-stage image still install `libpq5`?
8. Your password is `p@ss:word`. Write the connection string for user `notes`, host `db`, database `notes`. What breaks if you do not encode it?
9. What is the difference between `docker compose down` and `docker compose down -v`? When would `-v` be a mistake?
10. On ECS the frontend reaches the backend with `localhost:8000`, but in Compose with `backend:8000`. Why? Which one is right if the two were separate ECS services?
11. ECS showed the backend container as *Healthy*. Where did that health check come from, and why did the `HEALTHCHECK` in your Dockerfile not count?
12. Map each piece of your Compose file to its AWS equivalent in Part 7: the `db` service, the `back` network, the `.env` file, the `ports` entry, and `docker compose up`.

---

## What to submit

One PDF named `lab6-assignment-<yourname>.pdf` with:

1. The full text of: `backend/Dockerfile.single`, `backend/Dockerfile`, `backend/.dockerignore`, `frontend/Dockerfile`, `compose.yaml`, `.env.example`, and your task definition JSON **with the password replaced by `****`**. Do not include `.env`.
2. Screenshots A1 to A20, in order, each labelled with its ID.
3. The two tables: image sizes (Part 3) and broken connection strings (Part 5.7).
4. Answers to the 12 questions in Part 8.

**Grading (100 points)**

| Part | What is checked | Points |
| --- | --- | --- |
| 2 | Single-stage Dockerfile meets all 7 requirements; `.dockerignore`; A1, A2 | 10 |
| 3 | Multi-stage Dockerfile: builder stage, `--prefix`, `libpq5`, `COPY --from`; no `gcc` in the result; size table; A3 | 15 |
| 4 | Frontend Dockerfile; A4 explained | 5 |
| 5 | Correct connection string; DNS and isolation shown; broken-string table filled and explained; A5 to A7 | 15 |
| 6 | Compose file meets all 8 requirements; `DATABASE_URL` built from `.env`; isolation and volume proven; A8 to A11 | 25 |
| 7 | Images in ECR; RDS private; db-sg allows only app-sg; two-container task working against RDS; cleanup; A12 to A20 | 20 |
| 8 | Questions | 10 |

Deductions: a password or `.env` file in an image, Dockerfile or submitted file (-10); the database published on a host port or RDS set to public (-5); missing cleanup screenshot (-5).

## Stretch goals (not graded)

- **Secrets Manager:** store the connection string as a secret, give `ecsTaskExecutionRole` permission to read it (`secretsmanager:GetSecretValue`), and replace the `environment` entry with `"secrets": [{"name": "DATABASE_URL", "valueFrom": "<secret ARN>"}]`. Confirm the password no longer shows in the task definition.
- **Scale the backend:** `docker compose up -d --scale backend=3`, then `docker compose restart frontend` (nginx looks up `backend` only when it starts). Call `/api/info` 20 times and count the different `backend_hostname` values: Docker's DNS returns all three containers, and nginx spreads requests over them.
- **A tiny image:** try `python:3.12-alpine` as the runtime stage. What has to change in both stages, and is it worth it?
- **Two ECS services:** run the frontend and the backend as separate services connected with ECS Service Connect, so the frontend can reach `http://backend:8000` again, as in Compose.

## Troubleshooting

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `pg_config executable not found` | `libpq-dev` not installed before `pip install` | Part 2, Task 2.1. |
| `Failed building wheel for psycopg2` after a `gcc` command | `gcc` or `libc6-dev` missing | Install `gcc libc6-dev libpq-dev` together. |
| `ImportError: libpq.so.5` | Multi-stage runtime stage has no `libpq5` | Part 3. |
| `"db_error": "DATABASE_URL is not set"` | No `-e DATABASE_URL`, or a typo in the variable name | `docker exec backend env`. |
| `could not translate host name "db"` | The db container is not running, has another name, or is on another network | `docker ps`, `docker network inspect <network>`. |
| `Connection refused` on `localhost` | `localhost` is the backend container itself | Use the database's container or service name. |
| `password authentication failed` | Wrong password, or the volume was created earlier with another password | The image sets the password only on an empty volume: `docker compose down -v`, then `up`. |
| `database "notes" does not exist` | `POSTGRES_DB` differs from the name in the URL, or RDS created without *Initial database name* | Compare them. On RDS, create the database or recreate the instance. |
| nginx: `host not found in upstream "backend"` | No container named `backend` on the frontend's network | The service or container must be called `backend`, on the same network. |
| `502 Bad Gateway` from the page | nginx is up but the backend is not (yet) | `docker compose ps`, `docker compose logs backend`. |
| `port is already allocated` | Something else uses 8080 or 8000 | `docker ps`, or change the host side: `8081:80`. |
| `docker compose` reads no variables, `DATABASE_URL` has empty parts | `.env` is not in the same folder as `compose.yaml`, or has spaces around `=` | `docker compose config`. |
| ECS task stops with `exec format error` | Image architecture differs from the task definition | 7.1: match `cpuArchitecture` to the image. |
| ECS task stops with `CannotPullContainerError` | Public IP off, wrong image URI, or no ECR access | Lab 5 troubleshooting. |
| ECS task: `ResourceInitializationError ... log group does not exist` | The log group was not created | 7.6, the `aws logs create-log-group` command. |
| On AWS, `/api/info` shows `timeout expired` | db-sg does not allow 5432 from app-sg, or the task uses another security group | 7.5 and 7.7. |
| On AWS, `no pg_hba.conf entry ... no encryption` | SSL turned off in the connection string | Keep `?sslmode=require`. |

## Local cleanup

```bash
docker compose down -v
docker rm -f api-alone web-alone api-test frontend backend db 2>/dev/null
docker network rm notes-net 2>/dev/null
docker volume rm notes-data 2>/dev/null
docker rmi notes-backend:single notes-backend:multi notes-frontend:1.0
```
