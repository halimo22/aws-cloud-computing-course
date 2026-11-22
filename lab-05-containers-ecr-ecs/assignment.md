# Lab 5: VPC, EC2, Docker and ECS on AWS

## Overview

In this lab you build a small production-style network on AWS, package a web page as a Docker image, and run it on Amazon ECS twice: once on a public IP, and once hidden in a private subnet behind a load balancer. Everything is done in **us-east-1**.

> **Diagram:** Lab 5 architecture · 3 subnets, 2 EC2 instances, 2 ECS services (drawn in the original course doc).

Everything that faces the internet sits in a public subnet; the private task is reached only through the load balancer, and it talks to ECR and CloudWatch through VPC endpoints instead of the internet.

**By the end you will be able to:**

1. Design a VPC with a public and a private subnet and explain what makes a subnet "public".
2. Reach a private EC2 instance through a bastion host using SSH key forwarding or a proxy command.
3. Give a private subnet outbound internet access with a NAT gateway.
4. Pull the public halimo1/env-printer image from Docker Hub and push it to Amazon ECR, using AWS CloudShell and the AWS CLI.
5. Write an ECS task definition and run it as a Fargate service.
6. Put a private service behind an Application Load Balancer and reach AWS services through VPC endpoints.

**Before you start you need:**

- An AWS account (or lab account) with permission to use VPC, EC2, ECR, ECS, ELB, IAM and CloudWatch Logs.
- AWS CloudShell (the terminal icon in the console toolbar), which has the AWS CLI and Docker preinstalled (`aws sts get-caller-identity` must work there). Nothing to install on your computer.
- A terminal on your computer with `ssh` and `curl`.

**Naming rule:** prefix every resource with `lab5-<yourname>` (for example `lab5-sara-vpc`). Your prefix must be visible in every screenshot.

**What to submit:** one PDF named `lab5-<yourname>.pdf` containing every screenshot listed as **Screenshot Sn** below, in order, each labelled with its ID (S1, S2, ...), plus your answers to Part 9. Every screenshot must show the AWS console region or the terminal prompt, and your resource prefix.

**Cost warning:** the NAT gateway, load balancer and interface endpoints are billed by the hour (roughly $2 to $3 per day together). Finish the lab in one or two sittings and do Part 10 (cleanup) the same day.

**Screenshot rules:**

- Full window, not a cropped fragment. The AWS region selector (or your terminal prompt) must be visible.
- Your `lab5-<yourname>` prefix must be readable in each one.

## Part 1: VPC, subnets and routing

A **VPC** is your own private network inside AWS. You choose its IP range, split it into **subnets**, and decide where each subnet's traffic may go using **route tables**. A subnet is called *public* for one reason only: its route table sends `0.0.0.0/0` (all non-local traffic) to an **internet gateway**. Nothing else makes it public.

| Resource | Name | Setting |
| --- | --- | --- |
| VPC | `lab5-<yourname>-vpc` | CIDR `10.0.0.0/16` (65,536 addresses) |
| Subnet | `lab5-<yourname>-public-a` | `10.0.1.0/24`, us-east-1a |
| Subnet | `lab5-<yourname>-private-a` | `10.0.2.0/24`, us-east-1a |
| Internet gateway | `lab5-<yourname>-igw` | attached to the VPC |
| Route table | `lab5-<yourname>-public-rt` | `0.0.0.0/0` to the internet gateway; associated with public-a |

**Steps (VPC console):**

1. **Your VPCs > Create VPC**, choose *VPC only*, enter the name and CIDR above. After it is created, open **Actions > Edit VPC settings** and tick **Enable DNS hostnames**. *Why:* instances get DNS names, and later the VPC endpoints need DNS hostnames and DNS resolution to work.
2. **Subnets > Create subnet**, pick your VPC, and create both subnets from the table. For **public-a**, open **Actions > Edit subnet settings** and tick **Enable auto-assign public IPv4 address**. *Why:* instances launched there get a public IP automatically; the private subnet must never do this.
3. **Internet gateways > Create**, then **Actions > Attach to VPC**. *Why:* the gateway is the VPC's door to the internet. On its own it does nothing until a route points at it.
4. **Route tables > Create route table** named public-rt in your VPC. **Edit routes > Add route**: destination `0.0.0.0/0`, target your internet gateway. Then **Subnet associations > Edit** and tick public-a. *Why:* this one route is what makes public-a public.
5. Leave private-a on the VPC's **main** route table. It only has the `local` route, so the private subnet can talk inside the VPC and nowhere else (you change this in Part 3).

**Screenshot S1:** your VPC's details page showing the CIDR `10.0.0.0/16` and *DNS hostnames: Enabled*.

**Screenshot S2:** the Subnets list filtered to your VPC, showing both subnets, their CIDRs and availability zone.

**Screenshot S3:** public-rt's **Routes** tab showing `10.0.0.0/16 local` and `0.0.0.0/0 igw-...`.

**Screenshot S4:** public-rt's **Subnet associations** tab showing public-a, and the internet gateway list showing your gateway as *Attached*.

**Check yourself:** the `local` route cannot be deleted. It is how every subnet in a VPC reaches every other subnet.

## Part 2: Security groups, EC2 and bastion SSH

A **security group** is a stateful firewall attached to a network interface: you list what may come *in*, and replies to allowed traffic go back out automatically. You will launch one instance in each subnet. The public one acts as a **bastion** (jump host), the only way to reach the private one.

| Security group | Inbound rule | Why |
| --- | --- | --- |
| `lab5-<yourname>-public-sg` | SSH (22) from **My IP** (`x.x.x.x/32`) | Only your computer can try to log in. Never use `0.0.0.0/0` for SSH. |
| `lab5-<yourname>-private-sg` | SSH (22) from **source: public-sg** | Only machines wearing the public-sg group can log in. This follows the bastion even if its IP changes. |

**Steps (EC2 console):**

1. **Security Groups > Create security group** twice, in your VPC, with the rules above. Keep the default outbound rule (all traffic).
2. **Key Pairs > Create key pair** named `lab5-<yourname>-key`, type RSA or ED25519, format `.pem`. Move it to `~/.ssh/` and run `chmod 400 ~/.ssh/lab5-<yourname>-key.pem`. *Why:* ssh refuses keys that other users can read.
3. **Launch instance** `lab5-<yourname>-public-ec2`: Amazon Linux 2023, `t3.micro`, your key, your VPC, subnet public-a, auto-assign public IP **Enabled**, security group public-sg.
4. **Launch instance** `lab5-<yourname>-private-ec2`: same AMI, type and key, subnet private-a, auto-assign public IP **Disabled**, security group private-sg.
5. SSH to the public instance:

```bash
ssh -i ~/.ssh/lab5-<yourname>-key.pem ec2-user@<public-ec2-public-ip>
```

6. SSH to the private instance *through* the public one. The private instance has no public IP, so your laptop cannot reach it directly. Use either method:

```bash
# Method A: load the key into your ssh agent, then jump with -J
ssh-add ~/.ssh/lab5-<yourname>-key.pem
ssh -J ec2-user@<public-ec2-public-ip> ec2-user@<private-ec2-private-ip>

# Method B: give the key to both hops with a proxy command
ssh -i ~/.ssh/lab5-<yourname>-key.pem \
  -o ProxyCommand="ssh -i ~/.ssh/lab5-<yourname>-key.pem -W %h:%p ec2-user@<public-ec2-public-ip>" \
  ec2-user@<private-ec2-private-ip>
```

**Common mistake:** `ssh -i key -J bastion target` fails with *Permission denied (publickey)*. The `-i` flag only applies to the final hop, so the bastion is offered your default keys. Method A or B fixes this.

**Do not copy your private key onto the bastion.** Anyone who gets into that instance would then own your key.

**Screenshot S5:** the inbound rules of both security groups (private-sg must show public-sg as the source).

**Screenshot S6:** the Instances list showing both instances *Running*, with the public instance's public IP and the private instance's empty public IP column.

**Screenshot S7:** your terminal logged into the public instance, after running `hostname -I`.

**Screenshot S8:** your terminal logged into the private instance through the bastion, after running `hostname -I` (it must show a `10.0.2.x` address).

## Part 3: NAT gateway for the private subnet

Right now the private instance cannot reach the internet at all, so it cannot even run `sudo dnf update`. A **NAT gateway** fixes that one way: instances in the private subnet can start connections *out* to the internet, but nothing on the internet can start a connection *in*. The NAT gateway lives in the **public** subnet and uses an **Elastic IP** as its public address; every private instance appears to the outside world as that one IP.

**First, prove it is broken.** From the private instance (through the bastion) run `curl -m 5 https://checkip.amazonaws.com`. It should time out.

**Steps (VPC console):**

1. **NAT gateways > Create NAT gateway**: name `lab5-<yourname>-nat`, subnet **public-a** (not private!), connectivity type *Public*, **Allocate Elastic IP**. Wait until its state is *Available*.
2. **Route tables > Create route table** named `lab5-<yourname>-private-rt` in your VPC. **Edit routes > Add route**: `0.0.0.0/0` to your NAT gateway.
3. **Subnet associations > Edit** and tick **private-a**. *Why:* private-a moves off the main route table onto this one. The public subnet keeps sending `0.0.0.0/0` to the internet gateway; the private subnet now sends it to the NAT gateway, which forwards it through the internet gateway for you.
4. Wait one or two minutes. A brand-new NAT gateway or route can drop the first few packets while it settles.
5. From the private instance run:

```bash
ping -c 4 8.8.8.8
curl https://checkip.amazonaws.com
```

The ping should get 4 replies, and `checkip` should print your **NAT gateway's Elastic IP**, not the bastion's IP. That proves the traffic leaves through the NAT.

**Common mistakes:**

- NAT gateway created in the private subnet: it then has no route to the internet gateway itself, so nothing works.
- Route added but private-a still associated with the main route table: check the subnet's *Route table* field on its details page.
- Pinging the bastion's private IP fails: that is expected. public-sg only allows SSH, not ICMP.

**Screenshot S9:** the NAT gateway details showing state *Available*, subnet public-a and its Elastic IP.

**Screenshot S10:** private-rt's Routes tab showing `0.0.0.0/0 nat-...`, and its Subnet associations tab showing private-a.

**Screenshot S11:** the private instance's terminal showing the successful ping and the `checkip` output; the IP printed must match S9.

## Part 4: Pull the env-printer image from Docker Hub

You will not build an image. You will use **`halimo1/env-printer`**, a small public image on Docker Hub made for this lab. It is a web server on port 80 that answers every request with the **environment variables** inside its container, and prints the same list to its log when it starts. That lets you see exactly what configuration ECS hands your container.

A **container image** is a packaged file system plus the command to start it. Images are stored in **registries**: Docker Hub is the public default, Amazon ECR is AWS's private one. An image name has three parts, `registry/repository:tag`; with no registry, Docker assumes Docker Hub, so `halimo1/env-printer:v1` means `docker.io/halimo1/env-printer:v1`. **Pull** downloads an image from a registry, **push** uploads one. Images are made of **layers**, and each is transferred only once.

Every command in Parts 4 and 5 runs in **AWS CloudShell**: a terminal in your browser, opened from the AWS console, that already has the AWS CLI, Docker and your credentials. Nothing is installed on your computer.

**Steps:**

1. In the console (region us-east-1), click the **CloudShell** icon in the top toolbar. When the prompt appears, check who you are and that Docker is there:

```bash
aws sts get-caller-identity
docker --version
```

2. Pull the image from Docker Hub and list your images. Each *Pull complete* line is one layer:

```bash
docker pull halimo1/env-printer:v1
docker images
```

**Screenshot S13:** the `docker pull` output and `docker images` listing `halimo1/env-printer`.

## Part 5: Push the image to Amazon ECR with the AWS CLI

ECS could pull `halimo1/env-printer` straight from Docker Hub, so why copy it to **Amazon ECR**? Three reasons. ECR repositories are private and access is controlled with IAM, so AWS needs no Docker Hub login. ECR has no anonymous pull rate limits. And in Part 8 a task with no internet route can still pull from ECR through VPC endpoints, which it can never do for Docker Hub.

Stay in CloudShell.

1. Create the repository and keep its address in two shell variables:

```bash
aws ecr create-repository --repository-name lab5-<yourname>/env-printer --region us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/lab5-<yourname>/env-printer
echo $REPO
```

2. Log Docker in to ECR. The AWS CLI fetches a 12-hour token and pipes it to Docker, so no password is typed:

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
```

3. Give the image a second name that points at ECR, then push it. `docker tag` copies nothing; it is another name for the same image ID:

```bash
docker tag halimo1/env-printer:v1 $REPO:v1
docker images
docker push $REPO:v1
```

In `docker images` both names show the **same IMAGE ID**: one image, two names. The Docker Hub image is published for both x86_64 and ARM64; CloudShell runs on x86_64, so it pulled and now pushes only the x86_64 version. Keep your task definition on X86_64.

4. Confirm the push from the AWS CLI:

```bash
aws ecr describe-images --repository-name lab5-<yourname>/env-printer \
  --query 'imageDetails[].[imageTags[0],imageDigest,imageSizeInBytes]' --output table
```

CloudShell ends idle sessions after about 20 minutes and forgets shell variables. If `$REPO` is empty, run the `ACCOUNT=` and `REPO=` lines again.

**Screenshot S15:** the `create-repository` output showing `repositoryUri`.

**Screenshot S16:** *Login Succeeded*, the `docker images` output with both names and one IMAGE ID, and the `docker push` output.

**Screenshot S17:** the `describe-images` table showing tag `v1` and its `sha256:` digest.

**Screenshot S18:** the repository in the ECR console showing the same tag and digest. Copy the image URI; you need it in Part 6.

## Part 6: ECS task definition

A **task definition** is the recipe ECS follows to start your container: which image, how much CPU and memory, which ports, which IAM roles, where logs go and which environment variables to set. It is versioned: every edit creates a new **revision** (`:1`, `:2`, ...), and services run one specific revision.

| Setting | Value | Why |
| --- | --- | --- |
| Family name | `lab5-<yourname>-nginx` | Revisions are grouped under this name. |
| Launch type | AWS Fargate | AWS runs the servers; you never see or patch them. |
| OS / architecture | Linux / X86_64 | The image you pushed from CloudShell is the x86_64 version. |
| Network mode | `awsvpc` (forced by Fargate) | Each task gets its own network interface, private IP and security group, like a tiny EC2 instance. |
| CPU / memory | 0.25 vCPU / 0.5 GB | Enough for this small app and the cheapest Fargate size. |
| Task execution role | `ecsTaskExecutionRole` | Used by **ECS itself** to pull the image from ECR and write logs. |
| Task role | none | Used by **your code** to call AWS APIs (S3, DynamoDB, ...). env-printer calls none, so give it nothing. |
| Container name | `web` | You refer to this name when attaching a load balancer. |
| Image URI | your ECR URI from S18, ending `:v1` |  |
| Port mapping | container port 80, TCP, HTTP | The app listens on 80. |
| Environment variable | `APP_ENV` = `lab5` | See below. |
| Log collection | Amazon CloudWatch, on | Container output goes to log group `/ecs/lab5-<yourname>-nginx`. |

**Steps (ECS console):** **Task definitions > Create new task definition**, fill in the table above and create it. If `ecsTaskExecutionRole` does not exist, choose *Create new role* in that field; the console attaches the managed policy `AmazonECSTaskExecutionRolePolicy`.

**About environment variables.** `environment` entries are plain text: anyone who can read the task definition can read them, so use them only for settings like `APP_ENV=lab5` or `LOG_LEVEL=info`. Secrets such as database passwords go under `secrets` instead, as a reference to SSM Parameter Store or Secrets Manager:

```json
"environment": [ { "name": "APP_ENV", "value": "lab5" } ],
"secrets": [ { "name": "DB_PASSWORD", "valueFrom": "arn:aws:ssm:us-east-1:<account-id>:parameter/lab5/db-password" } ]
```

You do not need a secret for this lab. The env-printer page lists every variable the container sees, so after Part 7 you will find `APP_ENV=lab5` on it, next to variables ECS adds by itself such as `AWS_EXECUTION_ENV=AWS_ECS_FARGATE` and `AWS_REGION`. That is also why a real secret must never go into a container like this one: the page would publish it to anyone who can reach it.

**Mixing up the two roles is the most common ECS error.** If a task stops with *CannotPullContainerError* or *ResourceInitializationError*, look at the **execution** role and the network path to ECR, never the task role.

**Screenshot S19:** the task definition revision's **JSON** tab, scrolled so that `image`, `portMappings`, `environment`, `executionRoleArn`, `networkMode` and `cpuArchitecture` are all visible (two screenshots are fine).

## Part 7: ECS cluster and a public Fargate service

A **cluster** is a named group that tasks and services run in; with Fargate it is just a label, no servers. A **service** keeps a chosen number of copies of a task running: if a task crashes or stops, the service starts a replacement. You will first run the task the simple way, on a public IP in the public subnet.

**Steps:**

1. **EC2 > Security Groups > Create** `lab5-<yourname>-ecs-public-sg` in your VPC, inbound **HTTP (80) from My IP**.
2. **ECS > Clusters > Create cluster** `lab5-<yourname>-cluster`, infrastructure **AWS Fargate** only.
3. Open the cluster, **Services > Create**:
    - Compute: launch type **Fargate**.
    - Task definition: `lab5-<yourname>-nginx`, latest revision. Service name `lab5-<yourname>-web-public`, desired tasks **1**.
    - Networking: your VPC, subnet **public-a** only, security group ecs-public-sg, **Public IP: turned on**.
    - Load balancing: none.
4. Wait until the service's **Deployments** tab shows the rollout as *Completed* and *1/1 tasks running*.
5. Open the running task, copy its **Public IP**, and browse to `http://<task-public-ip>/`.
6. Open the task's **Logs** tab (or CloudWatch log group `/ecs/lab5-<yourname>-nginx`). You will see the variable list the app prints when it starts, then one access line per browser request.

*Why the public IP must be on:* the task pulls its image from ECR over the internet. In a public subnet, the only way out is the internet gateway, and that needs a public IP. With it turned off the task stops with *CannotPullContainerError*.

**This set-up has two weaknesses**, which Part 8 fixes. The task's IP changes every time it restarts, so there is no stable address to give users. And the task sits on the internet with its own public IP, protected only by its security group.

**Screenshot S20:** the service page showing *Active*, 1/1 tasks running and the deployment *Completed*.

**Screenshot S21:** the browser at the task's public IP showing the env-printer page with APP_ENV=lab5 and HOSTNAME=ip-10-0-1-x.ec2.internal, a name built from the task's private IP inside the VPC.

**Screenshot S22:** the task's log lines showing the start-up variable list (with APP_ENV=lab5) and your request (`GET / HTTP/1.1" 200`).

## Part 8: Private service behind a load balancer

This is how real services are run: the tasks live in the **private** subnet with no public IP, and the only thing on the internet is an **Application Load Balancer (ALB)**. The ALB has a stable DNS name, checks each task's health, and sends requests only to healthy tasks. The ALB reaches tasks by private IP through a **target group**.

### 8.1 A second public subnet

An ALB must sit in **at least two availability zones**, so that it survives the loss of one. Create subnet `lab5-<yourname>-public-b`, `10.0.3.0/24`, in **us-east-1b**, and associate it with **public-rt** (not the main route table, or it will not be public).

### 8.2 VPC endpoints: how a private task reaches AWS

The private task still has to pull its image from ECR and send logs to CloudWatch. Your NAT gateway from Part 3 could carry that traffic, but **VPC endpoints** keep it on AWS's private network and avoid NAT data charges. There are two kinds:

|  | Gateway endpoint | Interface endpoint |
| --- | --- | --- |
| How it works | Adds a route (a prefix list) to the route tables you choose | Places a network interface with a private IP in your subnet; private DNS makes the service's normal name resolve to that IP |
| Services | S3 and DynamoDB only | Most AWS services (ECR, CloudWatch Logs, SSM, ...) |
| Firewall | None (route only) | A security group |
| Cost | Free | About $7.30 per month per endpoint per AZ, plus $0.01 per GB |

ECR needs **three** endpoints, because a pull talks to three places: the **ECR API** (`ecr.api`, authentication and metadata), the **Docker registry** (`ecr.dkr`, the image manifest) and **S3** (the image layers themselves are stored there). Logs need a fourth, `logs`.

**NAT gateway or PrivateLink?** Interface endpoints are built on **AWS PrivateLink**. Both give a private subnet a way out without public IPs, but they reach different things by different paths:

|  | NAT gateway (Part 3) | PrivateLink interface endpoint |
| --- | --- | --- |
| What it is | A translator in a public subnet that swaps private source IPs for its Elastic IP | A network interface with a private IP in your own subnet, wired to one service |
| Reaches | Anything on the internet (Docker Hub, package mirrors, any API) | Only the one service it was created for |
| Path | Out through the internet gateway to public addresses | Stays on AWS's private network; needs no internet gateway or public IP |
| Who can start connections | Your instances only; nothing outside can connect in | Your VPC to the service only |
| Access control | Route tables | A security group on each endpoint |
| Cost | About $32 per month, plus $0.045 per GB | About $7.30 per month per endpoint per AZ, plus $0.01 per GB |

Use a NAT gateway when private machines need the general internet, for example `dnf update`. Use endpoints when they only need specific AWS services, or must never touch the internet. Real VPCs often run both, as this lab does: the NAT for general traffic, endpoints for heavy or sensitive AWS traffic such as image pulls.

1. Security group `lab5-<yourname>-endpoints-sg`: inbound **HTTPS (443) from `10.0.0.0/16`**. *Why:* interface endpoints are reached over HTTPS from anywhere inside the VPC.
2. **VPC > Endpoints > Create**, service `com.amazonaws.us-east-1.s3`, type **Gateway**, route table **private-rt**. *Watch out:* attach it to the route table private-a actually uses; on the main route table it does nothing for private-a.
3. Create three **Interface** endpoints, `com.amazonaws.us-east-1.ecr.api`, `com.amazonaws.us-east-1.ecr.dkr` and `com.amazonaws.us-east-1.logs`: your VPC, subnet private-a, security group endpoints-sg, **Enable DNS name** ticked.

### 8.3 Load balancer and target group

1. Security group `lab5-<yourname>-alb-sg`: inbound **HTTP (80) from My IP**.
2. Security group `lab5-<yourname>-ecs-private-sg`: inbound **HTTP (80) from source alb-sg**. *Why:* the tasks accept traffic from the load balancer and nothing else, not even from inside the VPC.
3. **EC2 > Target groups > Create**: target type **IP addresses** (Fargate tasks are registered by IP, not by instance), name `lab5-<yourname>-tg`, HTTP 80, your VPC, health check path `/`. Register no targets; ECS will do it.
4. **EC2 > Load balancers > Create > Application Load Balancer**: name `lab5-<yourname>-alb`, **Internet-facing**, IPv4, your VPC, subnets **public-a and public-b**, security group alb-sg, listener **HTTP 80 forwarding to your target group**.

### 8.4 The private service

In your cluster, **Services > Create** `lab5-<yourname>-web-private`: Fargate, the same task definition, desired tasks 1, subnet **private-a** only, security group ecs-private-sg, **Public IP: turned off**. Under **Load balancing** choose your existing ALB, the existing listener on port 80, and the existing target group; container `web:80`.

**Check it works:**

- The task reaches *Running* and shows a `10.0.2.x` private IP and **no public IP**.
- **Target groups > your TG > Targets** shows that same IP as *healthy*. ECS registered it for you.
- `http://<alb-dns-name>/` (from the load balancer's details page) shows your page.
- Stop the task by hand (**Tasks > Stop**). Watch the service start a new one with a new IP and register it, while the ALB address stays the same. Refresh the page: HOSTNAME now shows the new task's IP.

**If the task keeps stopping**, open it and read the *Stopped reason*. *ResourceInitializationError ... unable to pull* means an endpoint, its DNS setting, the endpoints-sg rule or the S3 route is missing. A target stuck *unhealthy* means ecs-private-sg does not allow port 80 from alb-sg.

**Screenshot S23:** the Endpoints list showing your four endpoints *Available*, with types Gateway and Interface visible.

**Screenshot S24:** the target group's Targets tab showing the task IP as *healthy*.

**Screenshot S25:** the private service's running task showing its private IP and no public IP.

**Screenshot S26:** your browser at the ALB's DNS name showing your page; the address bar must show the `...elb.amazonaws.com` name.

## Part 9: Written questions

Answer each in two to four sentences.

1. What single setting makes public-a a public subnet and private-a a private one? Point to the screenshot that proves it.
2. Why does private-sg use public-sg as its source instead of the bastion's IP address?
3. Why does `ssh -i key -J bastion target` fail, while Method A in Part 2 works?
4. Your private instance can reach the internet through the NAT gateway. Can someone on the internet open a connection to it? Explain why or why not.
5. What is the difference between `docker tag` and `docker push`? Did `docker tag` in Part 5 copy any data?
6. Through the load balancer, the page shows `HOSTNAME=ip-10-0-2-x.ec2.internal`, a private address. Why, and what does that tell you about where your request ended up? Which variables on the page did you never set, and who set them?
7. Explain the difference between the task **execution** role and the task role, with one example of what each is used for.
8. You already have a NAT gateway. Give one reason to keep the ECR and Logs endpoints anyway, and one reason to delete them.

## Part 10: Cleanup

Delete everything in this order. A VPC cannot be deleted while anything still has a network interface in it, so the order matters: things that *use* the network go first, the network itself goes last.

1. **ECS:** for both services, **Update** desired tasks to 0, then **Delete service**. Then delete the cluster.
2. **Load balancer**, then its **target group** (a target group in use by a listener cannot be deleted).
3. **VPC endpoints:** all four.
4. **NAT gateway:** delete it and wait for state *Deleted* (a few minutes). Then **Elastic IPs > Release** its address. *Why:* an Elastic IP left behind keeps billing even when attached to nothing.
5. **EC2:** terminate both instances.
6. **ECR:** delete the repository (tick *force* to delete its images too).
7. **VPC:** **Your VPCs > Actions > Delete VPC**. This also removes its subnets, route tables, internet gateway and security groups. If it refuses, it lists what still has a network interface in the VPC; delete that and retry.
8. **Key pair:** delete `lab5-<yourname>-key` in EC2 and the `.pem` file on your computer. Optionally deregister the task definition revisions; they cost nothing.

**Screenshot S27:** the Your VPCs list, the Elastic IPs list and the ECS Clusters list, with none of your `lab5-<yourname>` resources remaining.

### Troubleshooting

| Symptom | Most likely cause |
| --- | --- |
| SSH to the bastion times out | Your IP changed. Update public-sg's SSH rule to **My IP** again. |
| *Permission denied (publickey)* through `-J` | The key was not given to the jump hop. Use Method A or B from Part 2. |
| Private instance cannot reach the internet | NAT gateway in the wrong subnet, private-a still on the main route table, or the NAT was created less than two minutes ago. |
| Task stops with *CannotPullContainerError* (public service) | Public IP turned off, or the task is not in public-a. |
| Task stops with *ResourceInitializationError* (private service) | Missing endpoint, *Enable DNS name* not ticked, endpoints-sg missing the 443 rule, or the S3 gateway endpoint not on private-rt. |
| Target stays *unhealthy* | ecs-private-sg does not allow port 80 from alb-sg. |
| ALB address times out in the browser | alb-sg does not allow port 80 from your current IP. |
