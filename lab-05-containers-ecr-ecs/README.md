# AWS Session: Artifacts, Containers, ECR and ECS

## Session overview

Students learn what a deployable **artifact** is and how code is packaged (as a zip or as a container image). They then pull a public image from Docker Hub, push it to a private **ECR** repository, and run it as a service on **ECS with Fargate**. Plan about 70 minutes of theory (Parts 1 to 4) and about 110 minutes of hands-on work (Part 5). We start with IAM, because every step after it depends on who is allowed to do what.

**Prerequisites**

- A VPC with at least 2 public subnets in different AZs (from the networking labs).
- Security groups and ALB concepts from the previous session.
- An IAM user or role in your AWS account with permission to use ECR, ECS, and CloudWatch Logs, and to create IAM roles (needed to create the task execution role). Part 1 explains why.
- A place to run Docker. The easiest is **AWS CloudShell**, which includes Docker, so nothing is installed. Docker Desktop on a laptop also works. Docker has no console screen, so this is the one part of the lab that needs a terminal. Everything else is console clicks.

**Learning outcomes.** By the end, a student can:

- Explain IAM users, groups, roles, and policies, and choose between a user and a role.
- Read an IAM permissions policy and a role trust policy.
- Explain what an artifact is, and why we build it once and deploy it many times.
- Compare a zip package with a container image, and choose between them.
- Describe image layers, tags, and digests.
- Explain what environment variables are, and use them to configure an app without rebuilding it.
- Create an ECR repository, and push and pull an image.
- Explain the ECS building blocks: cluster, task definition, task, service.
- Explain the difference between the task execution role and the task role.
- Deploy, scale, update, and troubleshoot a Fargate service.

**Timing**

| Block | Minutes |
| --- | --- |
| Part 1: IAM users, roles, and policies (theory + short console exercise) | 20 |
| Part 2: Artifacts, packaging, and environment variables (theory) | 25 |
| Part 3: ECR (theory) | 10 |
| Part 4: ECS (theory) | 15 |
| Part 5, steps 1 to 3: repository, push, cluster | 35 |
| Part 5, steps 4 to 6: task definition, service, test | 35 |
| Part 5, step 7: break it and update | 20 |
| Part 5, step 8: environment variables | 20 |
| Discussion and teardown | 15 |

**What we build**

```
Docker Hub                 ECR (private)               ECS on Fargate
nginxdemos/hello  --pull-->  <prefix>-hello:1.0  --pull-->  service with 2 tasks
      (public image)   tag + push  (your registry)   (task definition 1.0)
```

---

## Part 1: IAM users, groups, roles, and policies

**AWS Identity and Access Management (IAM)** decides **who** can do **what** on **which** resources. It is global (not per Region), free, and every console click and API call passes through it. IAM answers two separate questions:

- **Authentication:** who are you? (a password, an access key, or an assumed role)
- **Authorization:** what are you allowed to do? (policies)

Everything later in this session depends on it: pushing to ECR, ECS pulling an image, and an app reading a secret are all IAM decisions.

### The identities

| Identity | What it is | Credentials | Use it for |
| --- | --- | --- | --- |
| **Root user** | The account owner, created with the account's email | Email and password, plus MFA | A few account-level tasks only. Lock it away, turn on MFA, and create no access keys. |
| **IAM user** | A person or application identity inside the account | Long-term: a console password and optional access keys | Individual people in a small account. Never share one between people. |
| **IAM group** | A collection of users | None | Giving the same permissions to many users at once. A group cannot be a principal and cannot contain groups. |
| **IAM role** | An identity with permissions that anyone or anything **trusted** can assume | **Temporary**, issued when the role is assumed | AWS services, applications, cross-account access, federated or single sign-on users |

Larger organizations usually replace IAM users with **IAM Identity Center** (single sign-on), which gives people temporary role sessions. The ideas are the same.

### Users vs roles

|  | IAM user | IAM role |
| --- | --- | --- |
| Belongs to | One person or app | Whoever assumes it, one at a time |
| Credentials | Long-lived password or access keys | Short-lived, issued by AWS STS (default 1 hour) |
| Rotation | Manual | Automatic |
| If leaked | Works until someone notices and deletes it | Expires on its own |
| Typical use | A teacher's or student's console login | An EC2 instance, an ECS task, a Lambda function |

A simple way to remember it: a user is **someone**, and a role is a **hat** that someone or something puts on for a while.

### Policies

A **policy** is a JSON document that lists permissions. It is attached to an identity (user, group, or role), or to a resource.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::my-class-bucket",
        "arn:aws:s3:::my-class-bucket/*"
      ]
    }
  ]
}
```

This policy lets the holder list one bucket and read its objects, and nothing else.

| Element | Meaning |
| --- | --- |
| `Effect` | `Allow` or `Deny` |
| `Action` | The API calls, written `service:Operation`, for example `ecr:PutImage`. `*` is a wildcard. |
| `Resource` | What the action applies to, written as an **ARN** |
| `Condition` | Optional extra rules, such as source IP, MFA required, or a required tag |
| `Principal` | Who the policy applies to. Used only in resource-based and trust policies. |

An **ARN** (Amazon Resource Name) names one resource uniquely: `arn:aws:<service>:<region>:<account-id>:<resource>`. For example, an ECR repository is `arn:aws:ecr:<region>:<account-id>:repository/<prefix>-hello`.

**Kinds of policy**

| Kind | Meaning | Example |
| --- | --- | --- |
| AWS managed | Written and updated by AWS. Reusable. | `AmazonECSTaskExecutionRolePolicy` |
| Customer managed | Written by you. Reusable, versioned. | A policy for one bucket |
| Inline | Embedded in a single user, group, or role. Not reusable. | A one-off permission for one role |
| Identity-based | Attached to a user, group, or role | All of the above |
| Resource-based | Attached to a resource, and names a principal | An S3 bucket policy, an ECR repository policy, a role's trust policy |

Other layers can only **limit** permissions: permissions boundaries and Organizations service control policies (SCPs).

### How AWS decides: the evaluation rules

1. Everything is **denied by default**.
2. An explicit **Allow** in an applicable policy grants access.
3. An explicit **Deny** anywhere always **wins** over any Allow.
4. A boundary or an SCP can remove access that a policy would otherwise grant.

So the answer to "am I allowed?" is yes only if some policy allows it, and nothing denies it.

### Roles in depth

Every role has **two** kinds of policy:

| Policy | Question it answers | Example |
| --- | --- | --- |
| **Trust policy** | **Who** may assume this role? | The ECS service, a specific user, another AWS account |
| **Permissions policy** | **What** can the role do once assumed? | Pull from ECR, write logs |

A trust policy for an ECS task role looks like this. `Principal` names the service that is allowed to put the role on:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**How assuming a role works**

1. Something trusted (a user, an AWS service, an app) asks the **Security Token Service (STS)** to assume the role, using `sts:AssumeRole`.
2. STS returns **temporary credentials**: an access key, a secret key, and a session token, which expire.
3. The caller uses them for AWS calls. Before they expire, they are renewed automatically.

AWS SDKs and the CLI find these credentials for you, so your code never handles keys.

**Common role types**

| Role | Assumed by | Example |
| --- | --- | --- |
| EC2 instance profile | An EC2 instance | An instance reading from S3 |
| ECS task execution role | ECS itself | Pull the image from ECR, write logs, read secrets |
| ECS task role | Your code in the container | Read S3 or write to DynamoDB |
| Lambda execution role | A Lambda function | Write logs, read a queue |
| Cross-account role | A user in another account | A partner or a central security account |

**Why roles beat access keys on a server or container**

- Access keys end up in Git, in images, and in logs, and they never expire on their own.
- Rotating them is manual, and easily forgotten.
- A role gives short-lived credentials automatically, with nothing stored on disk or in the artifact. This is the same principle as keeping secrets out of an image.

### How IAM shows up in this session

| Moment | Whose permission is used |
| --- | --- |
| Pushing an image to ECR from CloudShell | Your own console user or role |
| ECS pulling the image and writing logs | The **task execution role** |
| Injecting a secret as an environment variable | The **task execution role** |
| Your app calling S3 or DynamoDB | The **task role** |

### Best practices

- Turn on **MFA** for the root user and every human user, and do not use root for daily work.
- Grant **least privilege**: only the actions and resources the job needs. Start narrow, and add permissions when something fails.
- Give permissions to **groups or roles**, not to individual users.
- Use **roles, not access keys**, for anything running on AWS.
- Avoid `"Action": "*"` with `"Resource": "*"` except for throwaway experiments.
- Use **conditions** (MFA, source IP, tags) for sensitive actions.
- Review what is used with IAM Access Analyzer and the **Last accessed** information, and remove unused permissions and keys.

### Quick console exercise (10 minutes)

If students cannot open these pages, the instructor should check their IAM read permissions first.

1. Open **IAM -> Policies**, search for `AmazonECSTaskExecutionRolePolicy`, and open the **JSON** tab. List the actions. Which are about ECR, and which about logs? Which `Resource` does it use, and why is `*` needed for the ECR login token?
2. Open **IAM -> Users** and click your own user. On the **Permissions** tab, find where each policy comes from (a group or directly). On **Security credentials**, check whether MFA is on and whether any access keys exist.
3. Open **IAM -> Roles**, pick any existing service role, and compare its **Trust relationships** tab (who) with its **Permissions** tab (what).
4. Later, after Step 4 of the lab creates `ecsTaskExecutionRole`, open it and check that its trust policy names `ecs-tasks.amazonaws.com`.

### Questions for students

1. A script on an EC2 instance needs to read one S3 bucket. Would you create an IAM user with access keys, or a role? Why? (A role: no stored keys, temporary credentials, automatic rotation.)
2. A policy allows `s3:*` on a bucket, and another attached policy has an explicit Deny for `s3:DeleteObject`. Can the user delete an object? (No. An explicit Deny always wins.)
3. What is the difference between a role's trust policy and its permissions policy? (Who can assume it, versus what it can do.)
4. A new IAM user is created with no policies. What can they do? (Nothing, because everything is denied by default.)
5. Why should the root user not have access keys? (It has full power over the account and cannot be restricted, so a leaked key is the worst case.)

---

## Part 2: Artifacts and packaging

### What is an artifact

An **artifact** is the built, versioned, ready-to-run output of your code: the thing you actually deploy. Source code is what developers edit. The artifact is what servers run.

The key idea is **build once, deploy many**. You build the artifact one time, give it a version, store it, and promote the **same** artifact through test, staging, and production. Only configuration changes between environments, never the code. This removes the classic problem of "it worked in staging but not in production" because something was rebuilt differently.

Good artifacts are:

- **Versioned:** you can say exactly which build is running (`1.4.2`, or a Git commit).
- **Immutable:** once published, a version never changes. A fix is a new version.
- **Self-contained:** everything needed to run is inside, or declared next to it.
- **Stored in a repository:** not on someone's laptop.

### Common artifact types

| Artifact | Contains | Stored in | Runs on |
| --- | --- | --- | --- |
| Zip or jar/war file | Code and libraries | S3, CodeArtifact | Lambda, Elastic Beanstalk, app servers |
| Language package (wheel, npm tarball) | Reusable library | CodeArtifact, PyPI, npm | Other applications |
| AMI | A full machine image | EC2 (per Region) | EC2 instances |
| **Container image** | Code, libraries, runtime, and OS userland | **ECR**, Docker Hub | ECS, EKS, Lambda, anywhere with a container runtime |

Today we focus on the two most common ways to package an application: a **zip** and a **container image**.

### Packaging as a zip

A zip bundles your code and its dependencies into one file. The platform supplies the runtime (Python, Node.js, Java) and the operating system. For AWS Lambda, the steps look like this:

```bash
pip install -r requirements.txt -t package/     # install dependencies next to the code
cd package && zip -r ../function.zip . && cd .. # zip the dependencies
zip function.zip lambda_function.py             # add your code
```

You then upload `function.zip` to S3 or directly to Lambda.

**Strengths:** small, simple, fast to build and upload, no extra tooling, and the platform patches the runtime for you.

**Limits:**

- You depend on the runtimes and versions the platform offers.
- Native libraries must be compiled for the platform's OS, so a package built on a Mac or Windows laptop may not run.
- Lambda limits: 50 MB zipped for direct upload, 250 MB unzipped including layers.
- Your local environment and the platform can differ, which brings back "works on my machine".

### Packaging as a container image

A **container image** packages your code, its libraries, the language runtime, and the OS-level files it needs into one portable unit. A **container** is a running instance of an image, like a process started from a program.

**Image layers.** An image is a stack of read-only layers. Each instruction in a Dockerfile adds a layer. Layers are cached and shared, so if you change only your code, only the top layer is rebuilt and re-uploaded.

```
+---------------------------+  <- your code (changes often)
+---------------------------+  <- pip install dependencies
+---------------------------+  <- Python runtime
+---------------------------+  <- base OS files (for example Debian slim)
```

**Dockerfile.** The recipe for building an image. Here is one for the users/orders app from the ALB lab:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
ENV SERVICE=users TOKEN=none
EXPOSE 80
CMD ["python", "app.py"]
```

- `FROM` picks the base image.
- `COPY` adds your code as a layer.
- `ENV` sets default configuration, which can be overridden at run time.
- `CMD` is the command the container runs on start.

**Tags and digests.** An image is identified two ways:

| Identifier | Example | Properties |
| --- | --- | --- |
| Tag | `nginxdemos/hello:1.0` | A human-friendly label that can be moved to another image. |
| Digest | `nginxdemos/hello@sha256:ab12...` | A hash of the exact content. It never changes. |

Avoid relying on `latest` in production, because you cannot tell which version it is, and it can change under you. Use explicit version tags, and turn on **tag immutability** in ECR so a version tag can never be overwritten.

**Registries.** Images are stored in a registry: Docker Hub (public), GitHub Container Registry, or **Amazon ECR** (private, integrated with IAM). A full image name is `registry/repository:tag`.

### Zip vs container image

|  | Zip | Container image |
| --- | --- | --- |
| What it contains | Code and libraries | Code, libraries, runtime, and OS files |
| Runtime and OS | Provided and patched by the platform | You choose and you maintain them |
| Portability | Tied to the platform | Runs the same on a laptop, ECS, EKS, or Lambda |
| Size | Small (MB) | Larger (tens to hundreds of MB), up to 10 GB on Lambda |
| Reproducibility | Medium | High, because the whole environment is packaged |
| Build tooling | A zip utility | Docker and a Dockerfile |
| Typical home | S3 | ECR |
| Good fit | Simple functions, small apps | Microservices, complex dependencies, long-running services |

Neither is better in general. A small Lambda function is fine as a zip. A service with native libraries, or one that must run identically in many places, belongs in a container.

### Configuration: environment variables

An **environment variable** is a named value (a key and a value) that the operating system hands to a program when it starts. The program reads it by name. Examples: `PORT=80`, `LOG_LEVEL=info`, `DB_HOST=db.internal`.

**Why they matter for artifacts.** If an artifact is built once and promoted unchanged, anything that differs between environments (database address, feature flags, log level, API keys) cannot be baked into it. That configuration is supplied from outside when the program starts. Same image, different configuration: `SERVICE=users` on one task and `SERVICE=orders` on another. In the ALB lab, the app received `SERVICE` and `TOKEN` from `Environment=` lines in a systemd file. That was the same idea.

**Reading them in code**

| Language | Example |
| --- | --- |
| Python | `os.environ.get("SERVICE", "unknown")` |
| Node.js | `process.env.SERVICE` |
| Java | `System.getenv("SERVICE")` |
| Bash | `$SERVICE` |

Give optional variables a default, and make the app fail with a clear message when a required one is missing.

**Where the values come from**

| Where | How |
| --- | --- |
| Shell | `export SERVICE=users` |
| Dockerfile | `ENV SERVICE=users` sets a **default** inside the image. |
| `docker run` | `-e SERVICE=orders` or `--env-file file.env` **overrides** the default. |
| EC2 | User data scripts, or systemd `Environment=` |
| Lambda | Configuration, Environment variables |
| ECS task definition | Container, Environment variables. A value set here overrides the image's `ENV`. |
| Elastic Beanstalk | Configuration, Environment properties |

**Rules of thumb**

- Keep configuration in environment variables, not in code.
- **Never put secrets in the image, the Dockerfile, or Git.** Anyone who can pull the image can read them with `docker history` or `docker inspect`.
- Plain environment variables are visible in the console, in the task definition, and in `docker inspect`. For passwords and API keys, use **AWS Secrets Manager** or **SSM Parameter Store**. ECS can inject them as environment variables when the container starts.
- Variables are read at **startup**. Changing one means starting a new task (in ECS, a new task definition revision).
- Use `UPPER_SNAKE_CASE` names, and document each one for the next developer.
- Do not print secret values in logs.

### Questions for students

1. Why do we promote the same artifact from staging to production instead of rebuilding it? (To guarantee that what we tested is what we run.)
2. A teammate pushes a fixed build under the same tag `1.0`. What can go wrong? (Servers that already pulled `1.0` keep the old image, and you cannot tell which one runs. Use a new tag, and immutable tags.)
3. Your Python function works on your Mac but fails on Lambda because of a compiled library. Which packaging choice avoids this? (A container image built for the target platform.)
4. If you change one line of code, which layers of the image are rebuilt? (Only the code layer and the ones above it.)
5. The app needs a database password. Where should it live: in the Dockerfile, in a plain environment variable, or in a secret store? (A secret store such as Secrets Manager, injected at start. The Dockerfile bakes it into every copy of the image.)

---

## Part 3: Amazon ECR

**Amazon Elastic Container Registry (ECR)** is AWS's managed registry for container images. It stores images in **repositories**, controls access with IAM, and is the natural source for ECS, EKS, and Lambda.

### Core concepts

| Concept | Meaning |
| --- | --- |
| Registry | One per AWS account and Region. Its address is `<account-id>.dkr.ecr.<region>.amazonaws.com`. |
| Repository | A collection of versions of one image, for example `s07-hello`. |
| Image | A specific version, identified by tag and digest. |
| Image URI | `<account-id>.dkr.ecr.<region>.amazonaws.com/<repository>:<tag>` |

### Repository settings

| Setting | Options | Why it matters |
| --- | --- | --- |
| Visibility | Private (default), or ECR Public | Private needs IAM to pull. Public is visible to everyone. |
| Tag immutability | Mutable (default) or immutable | Immutable stops anyone overwriting a version tag. |
| Scan on push | On or off | Checks the image for known vulnerabilities when pushed. |
| Encryption | AES-256 (default) or KMS | Images are encrypted at rest. |
| Lifecycle policy | Rules to expire old images | Controls storage cost, for example keep the last 10 images. |
| Replication | Cross-Region or cross-account | Faster pulls and disaster recovery. |
| Pull through cache | Rule that caches an upstream registry such as Docker Hub | Avoids Docker Hub rate limits. |

### Authentication

ECR uses IAM instead of a separate username and password. You request a temporary **authorization token** from AWS (valid for 12 hours) and give it to Docker:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <registry>
```

The username is always `AWS`, and the password is the token. The IAM user or role needs permissions such as `ecr:GetAuthorizationToken` (account-wide), plus `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, and `ecr:PutImage` to push, and `ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer` to pull.

### The push workflow

1. **Pull** the image from the source (Docker Hub).
2. **Tag** it with the full ECR repository URI and a version.
3. **Log in** to ECR with the token.
4. **Push** it. Only layers ECR does not already have are uploaded.

### Questions for students

1. Why does ECR use a token that expires after 12 hours instead of a fixed password? (Short-lived credentials limit the damage if one leaks, and access stays under IAM control.)
2. What does lifecycle policy protect you from? (Unbounded storage growth, since ECR charges per GB-month.)
3. Who pulls images when ECS starts a task? (The ECS agent, using the task execution role.)

---

## Part 4: Amazon ECS

**Amazon Elastic Container Service (ECS)** runs and manages containers for you: it starts them, keeps the desired number running, replaces failed ones, and rolls out new versions.

### Building blocks

| Concept | What it is | Analogy from earlier labs |
| --- | --- | --- |
| Cluster | A logical group of capacity where tasks run | A VPC for containers |
| Task definition | A versioned blueprint: image, CPU, memory, ports, environment variables, roles, logging | A launch template |
| Task | One running instance of a task definition (one or more containers) | One EC2 instance |
| Service | Keeps N copies of a task running, replaces failed ones, performs deployments, can register tasks with a load balancer | An Auto Scaling group plus its target group registration |
| Container | One process defined inside a task definition | The app on the instance |

```
Cluster
  +-- Service (desired count 2)
        +-- Task (from task definition revision 3)
        |     +-- Container: hello (image from ECR)
        +-- Task
              +-- Container: hello
```

A task definition is **versioned in revisions**. Changing the image, CPU, or memory creates a new revision, and a service is pointed at the revision it should run.

### Where tasks run: launch types

|  | Fargate | EC2 |
| --- | --- | --- |
| Who manages servers | AWS (serverless) | You manage the EC2 instances in the cluster |
| Billing | Per second, for the CPU and memory you request | By instance, whether full or not |
| Setup | Simplest | More control (GPUs, special instance types, cheaper at large scale) |
| Used in this lab | **Yes** | No |

### Networking: awsvpc mode

With Fargate, each task gets its **own network interface (ENI)** in your subnet, with its own private IP and its own **security group**. A task behaves like a small EC2 instance on your network, so everything you learned about subnets, routes, and security groups applies directly.

Because the task must pull its image from ECR and send logs to CloudWatch, it needs a network path to those services:

| Where the task runs | How it reaches ECR and CloudWatch |
| --- | --- |
| Public subnet with a public IP | Through the internet gateway. **Used in this lab.** |
| Private subnet | Through a NAT gateway, or VPC endpoints for ECR (API and Docker), S3, and CloudWatch Logs |

### Two IAM roles, often confused

| Role | Used by | Purpose | Example permissions |
| --- | --- | --- | --- |
| **Task execution role** | ECS itself, before and around your container | Pull the image from ECR and write logs to CloudWatch | `AmazonECSTaskExecutionRolePolicy` |
| **Task role** | Your application code, inside the container | Call AWS services on the app's behalf | Read from S3, write to DynamoDB |

A simple way to remember it: the execution role lets ECS **start** your container, and the task role is what your container **can do** once it runs.

### Task execution role vs task role, in depth

Both roles are attached to the same task, both are trusted by `ecs-tasks.amazonaws.com`, and both are chosen in the task definition. The difference is **who uses them and when**.

**What happens, in order**

1. ECS starts a task. Before your container exists, ECS uses the **task execution role** to log in to ECR and pull the image, to create the log stream and send logs to CloudWatch, and to fetch any secrets or environment files it must inject.
2. The container starts, and your code runs.
3. When your code calls an AWS service, the AWS SDK automatically receives temporary credentials for the **task role**, through a local credentials endpoint that ECS provides inside the container. Your code never sees the execution role.

An analogy: the execution role is the **moving crew** that unpacks the van and sets up the house before you arrive. The task role is **your own house key**, which you use once you live there.

**Side by side**

|  | Task execution role | Task role |
| --- | --- | --- |
| Used by | ECS and Fargate, on your behalf | Your application code inside the container |
| When | Before and around container start | While the app is running |
| Set in the task definition as | Task execution role | Task role |
| Required? | Yes, for private ECR images, CloudWatch logs, and secrets. Not needed for public images with no logging. | No. Only if your code calls AWS services. |
| Typical permissions | `AmazonECSTaskExecutionRolePolicy`, plus `secretsmanager:GetSecretValue`, `ssm:GetParameters`, and `kms:Decrypt` if you inject secrets | Custom and narrow, for example `s3:GetObject` on one bucket |
| Visible to your code? | No | Yes, through the SDK's default credential chain |
| Scope | One per task definition, shared by every container in it | One per task definition, shared by every container in it |
| If missing or too narrow | The **task fails to start** or cannot log | The task runs, but the app's AWS calls fail with `AccessDenied` |

Because each task definition has its own task role, the users service and the orders service can have different, minimal permissions even in the same cluster.

**Example permissions**

Extra permission on the **execution role** so ECS can inject the secret from Step 8, Part D:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:<region>:<account-id>:secret:<prefix>/token-*"
}
```

Permission on the **task role** so the app itself can read one bucket:

```json
{
  "Effect": "Allow",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::my-class-bucket/*"
}
```

**Which role is wrong? Read the symptom**

| Symptom | Likely cause |
| --- | --- |
| `CannotPullContainerError` with "not authorized", task never starts | Execution role missing, or lacks ECR permissions |
| Task starts, but no logs appear in CloudWatch | Execution role lacks `logs:CreateLogStream` or `logs:PutLogEvents`, or the log group is missing |
| `ResourceInitializationError`: unable to pull secrets | Execution role lacks `secretsmanager:GetSecretValue` (or `kms:Decrypt`), or the secret ARN is wrong |
| App logs `AccessDenied` when calling S3 or DynamoDB | Task role missing, or lacks that permission |
| App logs `Unable to locate credentials` | No task role is attached to the task definition |

**Common mistakes**

- Adding S3 or DynamoDB permissions to the **execution** role. Your code cannot use that role, so the app still fails.
- Adding ECR or CloudWatch permissions to the **task** role. ECS does not use it to start the task.
- Giving both roles broad permissions "to make it work". Keep the execution role to the platform's needs, and keep the task role to what the app needs.

**One question settles it:** who is making the call? If it is ECS setting up or running my container, it is the **execution role**. If it is my own code, it is the **task role**.

**Check your understanding**

1. The image is in a private ECR repository and the task stops with `CannotPullContainerError`. Which role do you fix? (The execution role.)
2. The container runs, but the app gets `AccessDenied` reading a bucket. Which role do you fix? (The task role.)
3. You add the Secrets Manager permission to the task role, and the secret is still not injected. Why? (ECS injects secrets using the execution role, so the permission is in the wrong place.)
4. Do the lab tasks in Step 4 need a task role? (No. The nginx page and the Python app call no AWS services.)

### Services and deployments

- The service scheduler compares **desired count** with **running count**, and starts or stops tasks to match. This is self-healing.
- A new task definition revision triggers a **rolling deployment**: new tasks start, pass their checks, and then old tasks are stopped, so the service stays available.
- A **deployment circuit breaker** can detect a failing deployment and roll it back automatically.
- A service can be attached to an **ALB target group** (target type **IP** for awsvpc). The service registers and deregisters tasks for you.

### Questions for students

1. What is the difference between a task definition and a task? (Blueprint versus a running instance.)
2. A task keeps failing with `CannotPullContainerError`. Which role and which network path do you check first? (The task execution role, and whether the task can reach ECR.)
3. Your code needs to read an S3 bucket. Which role gets the S3 permission? (The task role, not the execution role.)
4. Why does a Fargate task in a private subnet need a NAT gateway or endpoints? (It must reach ECR and CloudWatch to start.)

---

## Part 5: Hands-on lab

Students take a public image from Docker Hub, push it to their own ECR repository, and run it as a service on ECS Fargate.

### Before you start

- Use one AWS Region for everything, and check it in the top-right corner of the console.
- Prefix every resource name with your student ID (for example `s07-`).
- Open **AWS CloudShell** (the terminal icon in the console's top bar), and run `docker version` to confirm Docker works. If your account does not allow it, use Docker Desktop on your laptop with the AWS CLI configured.
- Note your 12-digit **account ID** (top-right menu in the console).
- The public image is `nginxdemos/hello`: a tiny web page that shows the container's hostname and IP, so you can see which task answered.

### Step 1: Create the ECR repository

Goal: a private place in your account to hold the image.

1. Open **ECR -> Private registry -> Repositories -> Create repository**.
2. **Visibility:** Private. **Repository name:** `<prefix>-hello`.
3. Leave **Tag immutability** as mutable for now (we discuss it at the end), and turn **Scan on push** on.
4. Click **Create**. Open the repository and note its **URI**: `<account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello`.

**Checkpoint**

- [ ] The repository exists and is empty.
- [ ] Students can point to the account ID and Region inside the URI.

### Step 2: Pull from Docker Hub, tag, and push to ECR

Goal: copy the public image into your private registry.

In the ECR repository page, the **View push commands** button shows these commands with your values filled in. Run them in CloudShell:

```bash
# 1. Pull the public image from Docker Hub
docker pull nginxdemos/hello:latest
docker images

# 2. Tag it with your ECR repository URI and a version
docker tag nginxdemos/hello:latest <account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello:1.0

# 3. Log in to ECR with a temporary token
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# 4. Push
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello:1.0
```

What each command does:

- `docker pull` downloads the image layers to your machine. Docker Hub limits anonymous pulls (about 100 per 6 hours per IP), which matters in a class sharing one network.
- `docker images` lists local images. The same image now has one ID.
- `docker tag` adds a second name to the **same** image. Nothing is copied.
- `docker login` stores the token. If you skip it, the push fails with `no basic auth credentials`.
- `docker push` uploads the layers. You will see layer IDs with progress, and `Pushed` for each.

**Checkpoint**

- [ ] In the console, the repository now lists image tag **1.0**, with a size and a digest (`sha256:...`).
- [ ] After a minute or two, the **Scan** column shows a scan result.
- [ ] Students can say which part of the image name is the registry, the repository, and the tag.

### Step 3: Create the ECS cluster

Goal: a logical home for the tasks.

1. Open **ECS -> Clusters -> Create cluster**.
2. **Cluster name:** `<prefix>-cluster`.
3. Under **Infrastructure**, keep **AWS Fargate (serverless)** selected, and do not add EC2 capacity.
4. Click **Create**.

**Checkpoint**

- [ ] The cluster shows **Active** with 0 services and 0 tasks. No servers were created, which is the point of Fargate.

### Step 4: Create the task definition

Goal: describe how to run the image.

1. Open **ECS -> Task definitions -> Create new task definition**.
2. **Task definition family:** `<prefix>-hello-task`.
3. **Launch type:** AWS Fargate. **Operating system/Architecture:** Linux/X86\_64 (this matches CloudShell and most laptops; if you pushed from an Apple Silicon Mac, see the troubleshooting table).
4. **CPU:** 0.25 vCPU. **Memory:** 0.5 GB.
5. **Task role:** none (this app calls no AWS services). **Task execution role:** **Create new role**. This is the role ECS uses to pull from ECR and write logs.
6. **Container - 1:** name `hello`, **Image URI:** paste your full URI with the tag, for example `<account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello:1.0`. Container port **80**, protocol TCP.
7. Keep **Use log collection** on, so the container's output goes to CloudWatch Logs.
8. Click **Create**.

**Checkpoint**

- [ ] The task definition is listed as **revision 1**, status **ACTIVE**.
- [ ] Students can explain why the image URI has a specific tag instead of `latest`.

### Step 5: Create the service

Goal: keep two copies of the task running.

1. Open **ECS -> Clusters ->** your cluster **-> Services -> Create**.
2. **Compute options:** Launch type, **Fargate**, platform version Latest.
3. **Task definition:** family `<prefix>-hello-task`, revision latest. **Service name:** `<prefix>-hello-svc`. **Desired tasks:** **2**.
4. Under **Networking**: your VPC, select the **two public subnets**. For **Security group**, choose **Create a new security group** named `<prefix>-ecs-sg` with an inbound rule **HTTP, TCP 80, source Anywhere** (for a class lab; use **My IP** if you prefer). Turn **Public IP** on.
5. Leave load balancing off for now. Check that the **deployment circuit breaker** is enabled.
6. Click **Create**. The service moves tasks through **Provisioning**, **Pending**, then **Running**.

**Checkpoint**

- [ ] The service shows 2 of 2 tasks running after a few minutes.
- [ ] If a task stops immediately, students read the **Events** tab and the stopped reason before asking for help.

### Step 6: Test the service

1. Open the service, go to the **Tasks** tab, and click the first task.
2. In **Configuration -> Networking**, copy the **Public IP**.
3. Open `http://<public-ip>` in your browser. You see the hello page, with **Server address**, **Server name**, and the request URI.
4. Repeat for the second task. The **Server name** differs, because each task is a different container.
5. Open the task's **Logs** tab to see the container's access log, written to CloudWatch.

**Checkpoint**

- [ ] Both tasks answer, with different server names.
- [ ] Students can explain how the task's public IP, security group, and subnet route made this work.

**Questions**

1. The page loaded from the internet, but the image came from ECR. Which path did the image take, and which IP did the task use to pull it? (Task ENI public IP, through the internet gateway, to ECR.)
2. Why can we reach the task directly here, when we put instances behind an ALB in the last lab? (The task has a public IP and an open security group. In production we would put it in a private subnet behind an ALB.)

### Step 7: Break it, scale it, update it

Ask students to predict each result first.

**Experiment A: a task dies (self-healing)**

1. In the service's **Tasks** tab, select one task and choose **Stop**.
2. Watch the service. Within about a minute a new task is started, and the count returns to 2.

Talking point: the scheduler keeps the running count equal to the desired count. Nobody had to act.

**Experiment B: scale out**

1. Select the service, choose **Update**, and change **Desired tasks** to 4.
2. Watch four tasks run. Open two new public IPs and see two new server names. Set it back to 2.

Talking point: this is the manual version of what Auto Scaling does automatically.

**Experiment C: a bad image tag**

1. Open the task definition, choose **Create new revision**, and change the image tag to `9.9` (which does not exist). Save as revision 2.
2. Update the service to use revision 2.
3. Open the service's **Events** tab and a failing task's stopped reason. You see **CannotPullContainerError** with a "not found" message.
4. The deployment circuit breaker rolls back to revision 1, and the old tasks keep serving the whole time.

Talking point: a rolling deployment starts new tasks before stopping old ones, so a bad version never takes the service down.

**Experiment D: a successful new version**

1. In CloudShell, pull a different public tag, tag it as version 1.1, and push it:

```bash
docker pull nginxdemos/hello:plain-text
docker tag nginxdemos/hello:plain-text <account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello:1.1
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/<prefix>-hello:1.1
```

2. Create a new task definition revision with image tag `1.1`.
3. Update the service to that revision. Watch the rolling deployment in the **Deployments** section.
4. Reload a task's public IP. The page is now plain text instead of HTML.

Talking point: the version moved from 1.0 to 1.1 by changing one field in the task definition. Rolling back means pointing the service at the old revision.

### Step 8: Environment variables

Goal: change what an app does without rebuilding its image. This uses the Python app from the ALB lab, which reads `SERVICE` and `TOKEN` from the environment and returns them as JSON.

**Part A: build the image and see the variables locally**

1. In CloudShell, create a folder with the app and a Dockerfile:

```bash
mkdir hello-app && cd hello-app

cat > app.py << 'EOF'
import json, os, socket
from http.server import BaseHTTPRequestHandler, HTTPServer

SERVICE = os.environ.get("SERVICE", "unknown")
TOKEN = os.environ.get("TOKEN", "none")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "service": SERVICE,
            "served_by": socket.gethostname(),
            "token": TOKEN
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
EOF

cat > Dockerfile << 'EOF'
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
ENV SERVICE=users TOKEN=none
EXPOSE 80
CMD ["python", "app.py"]
EOF
```

2. Build the image and give it your ECR name (replace the placeholders):

```bash
REGISTRY=<account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t $REGISTRY/<prefix>-hello:2.0 .
```

3. Run it twice, with and without overrides, and compare:

```bash
docker run -d --name t1 -p 8080:80 $REGISTRY/<prefix>-hello:2.0
curl localhost:8080          # uses the defaults baked into the image
docker rm -f t1

docker run -d --name t2 -p 8080:80 -e SERVICE=orders -e TOKEN=B-2058 $REGISTRY/<prefix>-hello:2.0
curl localhost:8080          # same image, different output
docker rm -f t2
```

**Checkpoint**

- [ ] The first call returns `"service": "users"` and `"token": "none"` (the `ENV` defaults).
- [ ] The second call returns `orders` and `B-2058`, from the same image.

**Part B: push and deploy with variables set in ECS**

1. Log in to ECR again if your token is older than 12 hours, then push: `docker push $REGISTRY/<prefix>-hello:2.0`.
2. Open the task definition and choose **Create new revision**.
3. In the container, change the image tag to `2.0`. Under **Environment variables**, choose **Add environment variable** twice: key `SERVICE` with value `users`, and key `TOKEN` with value `A-7391`. Save the revision.
4. Update the service to the new revision and wait for the rolling deployment to finish.
5. Open a task's public IP in the browser. You see the JSON with `users` and `A-7391`.

**Part C: change the configuration only**

1. Create another revision. **Do not change the image.** Change `SERVICE` to `orders` and `TOKEN` to `B-2058`.
2. Update the service and watch the rolling deployment.
3. Reload a task's public IP. The JSON now says `orders` and `B-2058`.

Talking point: the image (2.0) never changed. The behaviour changed because the configuration did. This is "build once, deploy many" in practice.

**Part D (optional): keep the token in a secret**

A plain environment variable is readable by anyone who can open the task definition. A secret is not.

1. Open **Secrets Manager -> Store a new secret**. Choose **Other type of secret**, a plaintext value such as `S-9999`, and the name `<prefix>/token`. Copy the secret's **ARN** after it is created.
2. Open **IAM -> Roles -> `ecsTaskExecutionRole`**, and add an inline policy allowing `secretsmanager:GetSecretValue` on that secret's ARN. ECS reads secrets with the **task execution role**, before your container starts.
3. Create a new task definition revision. Remove the `TOKEN` variable, and add a new one with key `TOKEN`, type **ValueFrom**, and the secret ARN as its value.
4. Update the service. The page shows `S-9999`, but the value does not appear in the task definition.

If the new tasks fail with `ResourceInitializationError` mentioning secrets, the execution role lacks permission or the ARN is wrong. SSM Parameter Store with a SecureString parameter works the same way and has no per-secret charge for standard parameters.

**Questions**

1. Why does changing an environment variable need a new task, and not just a setting change on the running container? (The value is read once at start, so ECS starts new tasks from a new task definition revision.)
2. Which value is used when both the Dockerfile `ENV` and the task definition set `SERVICE`? (The task definition.)
3. Which role reads a secret on behalf of ECS, and which role would your code use to read the same secret itself? (The task execution role for injection; the task role for reading it in code.)

### Stretch goals

- **Put the service behind an ALB:** in the service wizard, add an Application Load Balancer with an **IP** target group, and use the ALB DNS name instead of task IPs. Move the tasks to private subnets, and add a NAT gateway or ECR endpoints.
- **Enable tag immutability** on the repository, then try to push `1.0` again and read the error.
- **Add a lifecycle policy** that keeps only the last 5 images.
- **Use an environment file:** store a `.env` file in S3 and reference it from the task definition.

### Troubleshooting

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `no basic auth credentials` on push | Not logged in to ECR | Run the `docker login` step again. |
| `denied` or token expired | The 12-hour token expired | Log in again. |
| `CannotPullContainerError`: timeout | Task cannot reach ECR | Public IP on, public subnet with an internet route, or NAT and endpoints for private subnets. |
| `CannotPullContainerError`: not found | Wrong URI or tag | Compare the image URI to the repository exactly. |
| `CannotPullContainerError`: not authorized | Execution role missing permission | The task execution role with the ECS task execution policy. |
| `exec format error` in logs | Image architecture does not match the task | Pushed an ARM image to an X86\_64 task. Rebuild or pull with `--platform linux/amd64`, or set the task to ARM64. |
| Task starts then stops at once | The container exited | The task's **Logs** tab and the **Stopped reason**. |
| Page does not load from the browser | Security group, route, or public IP | Inbound rule on port 80, subnet route to the internet gateway, public IP enabled. |
| Service stuck below desired count | Capacity or networking error | The service **Events** tab. |

### Discussion (10 minutes)

- What did ECR give us that Docker Hub did not? (Private, IAM-controlled, in our account and Region, scanning, and no pull limits.)
- How is an ECS service like the Auto Scaling group and target group from the earlier lab?
- Why is it safer to deploy a new image tag than to overwrite the old one?
- When would you choose a Lambda zip over a container on ECS?
- What would you change to run this in production? (Private subnets, an ALB, HTTPS, immutable tags, scanning, autoscaling, a task role with least privilege.)

### Teardown and cost

Fargate bills per second while tasks run. ECR bills for storage per GB-month, and public IPv4 addresses are billed per hour. Delete in this order:

1. **The service:** open it, choose **Delete**, and confirm (use **Force delete** if asked). This stops the tasks.
2. **The cluster.**
3. **Task definitions:** select each revision and choose **Deregister**.
4. **The ECR repository:** delete the images, then the repository.
5. **The security group `<prefix>-ecs-sg`.**
6. **The CloudWatch log group** `/ecs/<prefix>-hello-task`.
7. **The Secrets Manager secret**, if you created one in Step 8, and the inline policy you added to `ecsTaskExecutionRole`.

- [ ] Service deleted, with 0 running tasks.
- [ ] Cluster deleted.
- [ ] ECR repository deleted.
- [ ] Security group and log group deleted.

Instructor tip: after class, check **ECS -> Clusters** and the **ECR** repository list for any leftover resources with a student prefix.
