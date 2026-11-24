cd lab-06-docker-dockerfile

# ---------- Build ----------
docker build -f solution/Dockerfile            -t dockerlab:single app
docker build -f solution/Dockerfile.multistage -t dockerlab:multi  app
docker build -f solution/Dockerfile -t dockerlab:1.1 --build-arg APP_VERSION=1.1 app   # ARG
docker images dockerlab                                                               # compare sizes

# ---------- Run ----------
docker run -d --name web  -p 8080:8000 -v lab6-data:/data dockerlab:single
docker run -d --name web2 -p 8081:8000 -e GREETING="Hi class" dockerlab:1.1           # ENV override

# ---------- What the app shows ----------
curl localhost:8080          # FROM, WORKDIR, ENV, ARG, USER, hostname
curl localhost:8081          # same app: different greeting (-e) and version (--build-arg)
curl localhost:8080/visits   # VOLUME counter, call it a few times
curl localhost:8080/health   # what HEALTHCHECK calls

# ---------- Inside the running container ----------
docker exec web whoami                  # appuser (USER)
docker exec web pwd                     # /app (WORKDIR)
docker exec web ls -la /app /data       # only app.py and requirements.txt (.dockerignore)
docker exec web env                     # GREETING, APP_VERSION, DATA_DIR (ENV)

# ---------- The image itself ----------
docker history dockerlab:single         # one row per instruction, with the size each one added
docker inspect dockerlab:single --format '{{json .Config.Labels}}'      # LABEL
docker inspect dockerlab:single --format 'user={{.Config.User}} workdir={{.Config.WorkingDir}} ports={{json .Config.ExposedPorts}}'
docker inspect dockerlab:single --format 'cmd={{json .Config.Cmd}} entrypoint={{json .Config.Entrypoint}}'

# ---------- Health and logs ----------
docker ps                                               # STATUS: (health: starting), then (healthy)
docker inspect web --format '{{.State.Health.Status}}'
docker logs --tail 10 web                               # gunicorn request log, including /health checks

# ---------- The volume outlives the container ----------
docker rm -f web
docker run -d --name web -p 8080:8000 -v lab6-data:/data dockerlab:single
curl localhost:8080/visits              # the count continues from before

# ---------- Override CMD ----------
docker run --rm dockerlab:single python -c "print('CMD replaced')"

# ---------- Cleanup ----------
docker rm -f web web2
docker rmi dockerlab:single dockerlab:multi dockerlab:1.1
docker volume rm lab6-data