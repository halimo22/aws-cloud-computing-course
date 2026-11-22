# AWS Lab: Security Groups, Load Balancers and Microservices

## Lab overview

In this lab, students put two independent services (users and orders) behind one Application Load Balancer (ALB), lock the instances down with security groups, and then break the system on purpose to see how it fails. Plan about 40 minutes of theory (Parts 1 to 3) and about 90 minutes of hands-on work (Part 4).

**Prerequisites**

- A VPC from the previous lab with 2 public and 2 private subnets, each pair spread over 2 Availability Zones (AZs).
- No NAT gateway or VPC endpoint is required: the app uses only Python 3, which comes preinstalled on Amazon Linux 2023.
- AWS Management Console access. Everything in this lab is done in the console, so no command line is needed.

**Learning outcomes.** By the end, a student can:

- Explain what a security group is, and why it is stateful and allow-only.
- Reference one security group from another instead of using IP ranges.
- Describe how an ALB uses listeners, rules, target groups, and health checks.
- Route requests by URL path to separate services.
- Predict what a client sees (200, 404, 502, 503, 504) when instances or whole services fail.

**Timing**

| Block | Minutes |
| --- | --- |
| Part 1: Security groups (theory + demo) | 15 |
| Part 2: Load balancers (theory) | 15 |
| Part 3: Target groups (theory) | 10 |
| Part 4, steps 1 to 4: build | 45 |
| Part 4, steps 5 to 6: test and break it | 25 |
| Discussion and teardown | 20 |

**Target architecture**

> **Diagram:** architecture · 1 ALB, 2 target groups, 4 private instances (drawn in the original course doc).

The ALB is the only public component. Its rules send `/users*` and `/orders*` to separate target groups, and the instances accept traffic only from `alb-sg`.

## Part 1: Security groups

A security group (SG) is a virtual firewall attached to a network interface (ENI), so it protects an EC2 instance, an ALB, an RDS database, and so on. Every rule you write is an **allow** rule; anything not allowed is dropped.

### Core properties

| Property | What it means | Why it matters in the lab |
| --- | --- | --- |
| Allow-only | There are no deny rules. Traffic is allowed only if some rule matches. | To block something, remove the rule that allows it. |
| Stateful | If a request is allowed in, the reply is allowed out automatically (and the reverse). | You do not need a matching outbound rule for replies. |
| Instance-level | Attached to the ENI, not to the subnet. | Two instances in the same subnet can have different rules. |
| Many-to-many | One SG can attach to many resources, and one resource can have up to 5 SGs by default. All their rules are combined (union). | Any matching rule in any attached SG allows the traffic. |
| Region and VPC scoped | An SG belongs to one VPC. | You cannot attach a VPC A security group to a VPC B instance. |
| Evaluated as a whole | All rules are evaluated; there is no rule order or priority. | Unlike NACLs and ALB rules, you never ask which rule is first. |

### Anatomy of a rule

Every inbound rule has the same fields. Outbound rules are the same, with Destination instead of Source.

| Field | Options | Notes |
| --- | --- | --- |
| Type | SSH, HTTP, HTTPS, RDP, MySQL/Aurora, PostgreSQL, Custom TCP, Custom UDP, All traffic, and more | A shortcut that fills in protocol and port. |
| Protocol | TCP, UDP, ICMP, ICMPv6, or All | TCP covers most web and database traffic. ICMP is what ping uses. |
| Port range | One port (80), a range (8000-8100), or all | Ports 0-65535 with protocol All is the widest possible rule. |
| Source (inbound) / Destination (outbound) | A CIDR, another security group, a prefix list | See the next table. |
| Description | Free text | Always fill it. It is how you will understand the rule in 3 months. |

### The source options

| Source type | Example | Use it when | Watch out for |
| --- | --- | --- | --- |
| IPv4 CIDR | `0.0.0.0/0` (anyone), `203.0.113.7/32` (one address), `10.0.0.0/16` (the VPC) | Public services, or a known office or home IP. | `0.0.0.0/0` on SSH (22) or a database port exposes it to the whole internet. |
| IPv6 CIDR | `::/0` (anyone) | Same as above, for IPv6 traffic. | Often forgotten: allowing `0.0.0.0/0` does not cover IPv6. |
| My IP | The console fills in your current public IP as `/32` | Admin access during a lab. | It changes when your ISP address changes. |
| Another security group | `sg-0abc...` (for example `alb-sg`) | Traffic between tiers of an application. | Allows any resource attached to that SG, in the same VPC (or a peered VPC). |
| Prefix list | AWS-managed (for example the S3 or CloudFront ranges) or your own list | Many CIDRs managed in one place. | Counts against rule limits by its maximum size. |

**Rule of thumb:** use a CIDR for "the outside world", and a security group reference for "the other tier of my own application".

### Why reference a security group instead of an IP

In this lab the instances accept port 80 only from `alb-sg`. ALB nodes are created, replaced, and scaled by AWS, so their IP addresses change. A reference to `alb-sg` always matches the current ALB, and nothing else. It also means anyone who finds an instance's private IP still cannot reach it directly.

### Defaults to know

- **A new security group** has no inbound rules (all inbound is blocked) and one outbound rule allowing all traffic.
- **The default security group** of each VPC allows inbound traffic from members of itself and all outbound traffic. Avoid using it for real workloads.
- **Quotas** (adjustable): 60 inbound and 60 outbound rules per SG, 5 SGs per network interface.
- **Changes apply immediately** to existing connections' new packets. Tracked (already established) connections are not cut when you remove a rule, but new connections are blocked.

### Security groups vs Network ACLs

Students often confuse these two, so draw the comparison on the board.

|  | Security group | Network ACL (NACL) |
| --- | --- | --- |
| Attached to | Network interface (instance, ALB, and so on) | Subnet |
| Rule type | Allow only | Allow and deny |
| State | Stateful | Stateless (you must allow the return traffic, including ephemeral ports 1024-65535) |
| Evaluation | All rules together | In numbered order, first match wins |
| Default | Inbound denied, outbound allowed | Default NACL allows everything |
| Typical use | Main day-to-day firewall | Extra subnet-level guard rail, or blocking a specific bad IP range |

### Our two security groups

| Security group | Inbound rule | Outbound | Purpose |
| --- | --- | --- | --- |
| `alb-sg` | TCP 80 from `0.0.0.0/0` | Default (all) | The ALB is the public entry point. |
| `app-sg` | TCP 80 from `alb-sg` | Default (all) | Instances only accept traffic that came through the ALB. |

**Questions to ask students**

1. A security group has no deny rule. How would you block one bad IP while allowing everyone else? (Use a NACL.)
2. If `app-sg` has no outbound rule at all, can the instance still answer the ALB's request? (Yes, because security groups are stateful.)
3. We allow `alb-sg` as a source. Does that mean the instance accepts traffic from a student's laptop through the ALB? (Yes, that is the point: the ALB, not the laptop, is the source the instance sees.)

## Part 2: Load balancers

A load balancer is a single, stable entry point that spreads incoming requests across several targets, stops sending traffic to unhealthy ones, and lets you add or remove targets without clients noticing. It gives you three things a single EC2 instance cannot: **availability** (survive an instance or AZ failure), **scalability** (add targets as load grows), and **a clean boundary** (one public address in front of private instances).

### Elastic Load Balancing types

| Type | OSI layer | Understands | Typical use |
| --- | --- | --- | --- |
| Application Load Balancer (ALB) | 7 (HTTP/HTTPS, gRPC, WebSocket) | Paths, hostnames, headers, query strings, cookies | Web apps and microservices. **Used in this lab.** |
| Network Load Balancer (NLB) | 4 (TCP, UDP, TLS) | IP and port only | Extreme performance, static IPs, non-HTTP protocols. |
| Gateway Load Balancer (GWLB) | 3 | IP packets | Inserting firewalls and inspection appliances. |
| Classic Load Balancer | 4 and 7 | Basic | Legacy. Do not use for new work. |

### ALB building blocks

| Component | What it is | In our lab |
| --- | --- | --- |
| Load balancer | The managed resource. It places one node per subnet you select, which is why you pick at least 2 AZs. | `alb`, in the 2 public subnets |
| Scheme | Internet-facing (public IPs) or internal (private IPs only) | Internet-facing |
| Security group | Controls who can reach the ALB | `alb-sg` |
| Listener | Checks for connections on a protocol and port (HTTP:80, HTTPS:443) | HTTP:80 |
| Rule | A condition (path, host, header, and so on) plus an action | `/users*` and `/orders*` |
| Action | Forward to a target group, redirect, or return a fixed response | Forward, plus a fixed 404 default |
| Target group | A set of targets with one health check configuration | `users-tg` and `orders-tg` |
| Target | An instance, an IP address, a Lambda function, or another ALB | 2 EC2 instances per target group |
| Health check | A periodic request the ALB sends to each target | `GET /health` every 10 s |

### How a request flows

1. The client resolves the ALB DNS name, which returns the IPs of the ALB nodes (one per AZ).
2. The request reaches the ALB node. The ALB security group must allow the client's source on the listener port.
3. The listener evaluates its rules in **priority order** (lowest number first). The first rule whose condition matches decides the action.
4. If no rule matches, the **default action** runs. In this lab that is a fixed 404 response.
5. A forward action picks a healthy target in the chosen target group and opens a new connection to it. The instance security group must allow the ALB's security group.
6. The response travels back through the ALB to the client.

### Rule conditions and actions

| Condition | Example | Example use |
| --- | --- | --- |
| Path pattern | `/users*` | Split one site into services. **Used in this lab.** |
| Host header | `api.example.com` | One ALB for several domains. |
| HTTP header | `User-Agent: Mobile*` | Route by client type. |
| HTTP method | `POST` | Separate reads from writes. |
| Query string | `version=2` | Canary or version routing. |
| Source IP | `203.0.113.0/24` | Office-only admin paths. |

| Action | What it does |
| --- | --- |
| Forward | Sends traffic to one or more target groups (can be weighted, for example 90/10). |
| Redirect | Returns a 301/302, for example HTTP to HTTPS. |
| Fixed response | Answers directly from the ALB, with a status code, content type, and body. |
| Authenticate | Requires login with Cognito or an OIDC provider before forwarding. |

### Cross-zone load balancing

With cross-zone load balancing, each ALB node can send traffic to targets in every AZ, so load is spread evenly across all targets. It is always on for an ALB, and does not incur inter-AZ data charges for the ALB's own traffic.

### What the client sees: status codes

| Code | Who produced it | Typical cause |
| --- | --- | --- |
| 200 | Target | Healthy request. |
| 404 | ALB (fixed response) or the app | No rule matched and the default is a fixed 404, or the app does not know the path. |
| 502 Bad Gateway | ALB | The target closed the connection or sent an invalid response. |
| 503 Service Unavailable | ALB | The target group has **no registered targets**. |
| 504 Gateway Timeout | ALB | The target did not answer in time, which includes stopped instances when all targets are unhealthy. |

When **every** target in a group is unhealthy, the ALB **fails open**: it sends requests to all targets anyway, rather than refusing them. That is why a fully stopped service in this lab gives 504 (or 502) and not 503.

### Question for students

Why does the ALB need subnets in at least two AZs, and why do we put the **instances** in private subnets but the **ALB** in public subnets? (The ALB is the only component clients must reach, so it holds the public address. The private instances are reachable only through it.)

## Part 3: Target groups

A target group is the list of destinations an ALB can send requests to, together with the rules for checking their health and choosing among them. The ALB never talks to instances directly: a listener rule points to a target group, and the target group picks a healthy target.

```
Listener rule  →  Target group  →  Target (instance, IP, Lambda)
  /users*          users-tg          users-1, users-2
```

### How target groups relate to the rest

- A listener rule's **forward** action points to one target group, or to several with weights.
- One target group can be used by several rules, and a target can be registered in several target groups (for example the same instance on two ports).
- Health checks, routing algorithm, stickiness, and draining are all set **per target group**, not per ALB. That is why users and orders can behave differently.
- A target group does nothing until a rule points to it. Until then its targets show **Unused**.

### Target types

The type is chosen when you create the target group and cannot be changed later.

| Target type | You register | Typical use |
| --- | --- | --- |
| Instance | EC2 instance IDs. Traffic goes to the instance's primary private IP. | EC2 and Auto Scaling groups. **Used in this lab.** |
| IP | Private IP addresses | ECS Fargate tasks, containers with their own IP, on-premises servers over VPN or Direct Connect. |
| Lambda | One Lambda function | Serverless back ends behind an ALB. |
| ALB | An Application Load Balancer | An NLB that forwards to an ALB. |

### Target group settings

| Setting | Options | Effect |
| --- | --- | --- |
| Protocol and port | HTTP or HTTPS, port number | The port on the target that receives traffic. |
| Protocol version | HTTP1 (default), HTTP2, gRPC | How the ALB talks to the target. |
| Health check path | `/health`, `/status`, and so on | The URL requested on each target. |
| Health check port | Traffic port (default) or an override | Check a different port than the one serving traffic. |
| Interval | 5 to 300 seconds (default 30) | How often a target is checked. |
| Timeout | 2 to 120 seconds (default 5) | How long to wait for a reply before counting a failure. |
| Healthy threshold | 2 to 10 (default 5) | Consecutive successes before a target is marked healthy. |
| Unhealthy threshold | 2 to 10 (default 2) | Consecutive failures before a target is marked unhealthy. |
| Success codes | 200 (default), or a range such as 200-299 | HTTP codes counted as healthy. |
| Routing algorithm | Round robin (default), least outstanding requests, weighted random | How the next target is picked. |
| Stickiness | Off, or on with a cookie and duration | Keeps one client on one target. |
| Deregistration delay | 0 to 3600 seconds (default 300) | How long in-flight requests may finish before a target is removed. |
| Slow start | Off (default), or 30 to 900 seconds | Gradually raises a new target's share of traffic. |

The lab sets interval 10 s and healthy threshold 2 so students do not wait long. The AWS defaults are slower.

### How health checks work

Every ALB node sends its own `GET` request to each registered target on the health check path, and the result decides the target's state. This is why `app-sg` must allow `alb-sg`: the checks come from the ALB.

Timing is roughly interval × threshold:

| Case | Detect a failure (interval × unhealthy) | Recover (interval × healthy) |
| --- | --- | --- |
| This lab (10 s, 2 and 2) | about 20 s | about 20 s |
| AWS defaults (30 s, 2 unhealthy, 5 healthy) | about 60 s | about 150 s |

Short intervals detect failures faster but add check traffic and can mark a slow target unhealthy too eagerly. Long ones are gentler but slower to react.

### Target states

| State | Meaning | Gets traffic? |
| --- | --- | --- |
| initial | Being registered, or the first health checks are running | No |
| healthy | Passed the required number of checks | Yes |
| unhealthy | Failed the required number of checks | No (unless every target is unhealthy, see below) |
| unused | Target group has no listener rule, or the target's AZ is not enabled on the ALB | No |
| draining | Being deregistered, finishing in-flight requests | Existing requests only |
| unavailable | Deregistration finished or the target is not responding | No |

If **every** target in the group is unhealthy, the ALB **fails open** and sends traffic to all of them anyway. If the group has **no registered targets**, the ALB returns 503.

### Choosing a target

- **Round robin** sends each new request to the next target in turn, but it is not strict alternation across a whole ALB, because each ALB node keeps its own rotation.
- **Least outstanding requests** sends the request to the target with the fewest requests in progress. It suits requests with very different durations.
- **Stickiness** pins a client to one target with a cookie. It helps apps that keep session data in memory, but it weakens even distribution and hides failures. Prefer a shared session store.
- **Cross-zone load balancing** is always on for an ALB, so each node can use targets in every AZ.

### Registering and deregistering

When you **deregister** a target, it moves to **draining**. The ALB stops sending new requests, lets in-flight ones finish for the deregistration delay (300 s by default), and then removes it. In a lab, lowering the delay to 30 s saves waiting. In production, set it longer than your slowest request.

### Weighted target groups (canary releases)

A forward action can list two target groups with weights, for example 90 and 10. The ALB sends about 10% of requests to the new version, so you can test it with real traffic and shift the weights as confidence grows. Rolling back means setting the weight to 0.

### Our lab's target groups

|  | `users-tg` | `orders-tg` |
| --- | --- | --- |
| Type, protocol, port | Instance, HTTP, 80 | Instance, HTTP, 80 |
| Targets | `users-1` (AZ-a), `users-2` (AZ-b) | `orders-1` (AZ-a), `orders-2` (AZ-b) |
| Health check | `/health`, 10 s, healthy 2, success code 200 | `/health`, 10 s, healthy 2, success code 200 |
| Used by | Rule `/users*`, priority 10 | Rule `/orders*`, priority 20 |

### Troubleshooting unhealthy targets

| What you see | Likely cause | What to check |
| --- | --- | --- |
| Reason: Timeout, or targets never turn healthy | The ALB cannot reach the target | `app-sg` inbound rule from `alb-sg`, correct port, app running, target in a subnet of an enabled AZ |
| Reason: Response code mismatch | The path answers with a code that is not in the success codes | Health check path, redirects (301/302), success codes |
| Health check works in the browser but fails in AWS | Wrong health check port or protocol | The health check port override, and HTTP vs HTTPS |
| Stuck in **initial** | The target needs more checks before it is healthy | Interval × healthy threshold, and the app's startup time |
| **Unused** | Nothing points to the target group | The listener rules, and the AZs enabled on the ALB |
| All targets unhealthy, but requests still return 5xx | The ALB failed open | Fix the health check first, then retest |

In the console, open **Target Groups → select the group → Targets**. The **Health status details** column shows the reason code for each target.

### Questions for students

1. Who sends the health check requests, and which security group rule makes them possible? (The ALB nodes; the `alb-sg` source rule on `app-sg`.)
2. With interval 30 s and unhealthy threshold 2, how long can a dead instance keep receiving requests? (Up to about 60 s.)
3. A target group shows all targets as **unused**. What is the most likely cause? (No listener rule forwards to it.)
4. Why might you choose least outstanding requests over round robin? (Requests take very different times, so some targets would pile up.)

## Part 4: Hands-on lab

Students build the system in the console (about 45 minutes). Everything is done in the AWS Management Console, and testing is done in a web browser. No command line is needed.

### Before you start

- Use one AWS Region for everything, and check it in the top-right corner of the console.
- Prefix every resource name with your student ID (for example `s07-`), so shared accounts stay readable.
- Write down your VPC ID, the two public subnet IDs, and the two private subnet IDs. You will need them in every step.

### Step 1: Create the security groups

Goal: one SG for the public ALB, and one for the private instances that trusts only the ALB.

1. Open **EC2 → Security Groups → Create security group**.
2. Create **`<prefix>-alb-sg`**: your VPC, description "ALB", inbound rule **HTTP, TCP 80, source Anywhere-IPv4 (`0.0.0.0/0`)**. Leave outbound as the default.
3. Create **`<prefix>-app-sg`**: your VPC, description "App instances", inbound rule **HTTP, TCP 80, source = Custom, then pick `<prefix>-alb-sg`** from the list (do not type an IP range).

**Checkpoint**

- [ ] `app-sg` shows its source as an `sg-...` ID, not a CIDR.
- [ ] Neither SG has an SSH rule. Ask: how would you log in to a private instance without one? (Session Manager, or a bastion.)

### Step 2: Launch the four service instances

Goal: two copies of each service, one in each AZ, with no public IP.

1. Open **EC2 → Launch instances**. Launch four instances in total, using these settings:
   - **AMI:** Amazon Linux 2023. **Type:** t3.micro. **Key pair:** proceed without one.
   - **Network:** your VPC and the **private** subnet from the table below. **Auto-assign public IP: Disable.**
   - **Security group:** select existing, then `<prefix>-app-sg` only.
   - **Advanced details → User data:** paste the script below.
2. Name and place the instances like this:

| Name | Service | Subnet |
| --- | --- | --- |
| `<prefix>-users-1` | users | private, AZ-a |
| `<prefix>-users-2` | users | private, AZ-b |
| `<prefix>-orders-1` | orders | private, AZ-a |
| `<prefix>-orders-2` | orders | private, AZ-b |

In the script, change `SERVICE` to `orders` for the orders instances. If your quiz or class uses a token, set it too.

```bash
#!/bin/bash
SERVICE="users"      # change to "orders" on the orders instances
TOKEN="A-7391"       # unique value, returned in every response

mkdir -p /opt/app
cat > /opt/app/app.py << 'EOF'
import json, os, socket
from http.server import BaseHTTPRequestHandler, HTTPServer

SERVICE = os.environ.get("SERVICE", "unknown")
TOKEN = os.environ.get("TOKEN", "none")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "service": SERVICE,
            "served_by": socket.gethostname(),
            "path": self.path,
            "token": TOKEN
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
EOF

cat > /etc/systemd/system/app.service << EOF
[Unit]
Description=Lab microservice
After=network.target

[Service]
Environment=SERVICE=${SERVICE}
Environment=TOKEN=${TOKEN}
ExecStart=/usr/bin/python3 /opt/app/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now app
```

The app answers **every** path with HTTP 200 and a small JSON body naming the service, the instance that served it, and the token. That means any health check path works. It runs as a systemd service, so it restarts after a reboot or crash.

**Checkpoint**

- [ ] Four instances are **Running**, each with a private IP and **no** public IPv4 address.
- [ ] Each instance has only `app-sg` attached.

### Step 3: Create the target groups

Goal: group each service's instances so the ALB can route to them and check them.

1. Open **EC2 → Target Groups → Create target group**.
2. Settings for both: **Instances**, protocol **HTTP**, port **80**, your VPC, protocol version HTTP1.
3. Create **`<prefix>-users-tg`**. Under health checks, set path `/health`. Under advanced health check settings, set interval **10 s** and healthy threshold **2**. Register `users-1` and `users-2` (**Include as pending below**, then **Create**).
4. Create **`<prefix>-orders-tg`** the same way, and register `orders-1` and `orders-2`.

**Checkpoint**

- [ ] Both target groups list their two instances, and the status reads **Unused**. That is expected: a target group is not health-checked until an ALB listener points to it (Step 4).
- [ ] Students can explain what the health check requests, and who sends it. (The ALB nodes do. This is why `app-sg` must allow `alb-sg`.)

### Step 4: Create the Application Load Balancer

Goal: one public entry point that sends `/users*` and `/orders*` to the right service.

1. Open **EC2 → Load Balancers → Create load balancer → Application Load Balancer**.
2. **Name:** `<prefix>-alb`. **Scheme:** Internet-facing. **IP type:** IPv4.
3. **Network mapping:** your VPC, and select the **two public subnets**, one in each AZ.
4. **Security group:** remove the default one and select `<prefix>-alb-sg`.
5. **Listener:** HTTP:80. For the default action, choose any target group for now, and click **Create load balancer**.
6. Open the new ALB's **Listeners and rules** tab, and edit the HTTP:80 listener. Change the **default action** to **Return fixed response**: code 404, content type `text/plain`, body `No such service`.
7. **Add rule:** name `users`, condition **Path** `/users*`, action **Forward to** `users-tg`, priority **10**.
8. **Add rule:** name `orders`, condition **Path** `/orders*`, action **Forward to** `orders-tg`, priority **20**.

**Checkpoint**

- [ ] ALB state is **Active** (this takes a few minutes).
- [ ] The listener shows 2 rules plus the default.
- [ ] Both target groups now show the ALB attached, with targets **healthy**.

### Step 5: Test routing and load balancing

Find the ALB's address: **EC2 → Load Balancers →** select `<prefix>-alb` and copy the **DNS name** from the details pane. Then test in your browser. Type `http://` at the start yourself, because the ALB has no HTTPS listener.

Open each address in a browser tab:

| Address | Expected result |
| --- | --- |
| `http://<alb-dns>/users` | JSON with `"service": "users"` and your token |
| `http://<alb-dns>/orders` | JSON with `"service": "orders"` |
| `http://<alb-dns>/something-else` | The text `No such service` (the ALB's own 404 reply) |

To see load balancing, reload `http://<alb-dns>/users` ten times (hard reload: Ctrl+F5, or Cmd+Shift+R on Mac). Each time, note the `served_by` value and keep a tally for each hostname.

Students should see two hostnames. The split is roughly even but **not** strict alternation, because the ALB spreads requests across targets and across its own nodes. If the browser also requests `/favicon.ico`, that request hits the 404 rule, which is expected.

Then confirm it in the console: open **Target Groups → users-tg → Targets** and check that both targets are **healthy**. The **Monitoring** tab shows request graphs a few minutes later.

**Checkpoint**

- [ ] Both services answer through the same DNS name.
- [ ] The unknown path returns the custom 404.
- [ ] The instances cannot be reached directly from the internet (they have no public IP, and `app-sg` allows only `alb-sg`).

**Questions**

1. Which component decided that `/orders/42` goes to `orders-tg`? (The listener rule with priority 20.)
2. What would happen if the `/orders*` rule had priority 5 and a catch-all `/*` rule had priority 1? (The catch-all would win, since lower numbers are evaluated first.)
3. The app returns the same data on any path. How would a real app tell `/users` from `/health`? (It would route on the path itself, and `/health` would be a cheap check that does not hit the database.)

## Step 6: Break it on purpose

Goal: see how the system behaves when parts fail. Ask students to **predict the result before each action**, then compare. Restore the system after each experiment (start stopped instances, re-register targets, re-add rules) so the next one starts from a working state.

### Experiment A: one instance fails

1. Stop `users-1` (**EC2 → Instances →** select it **→ Instance state → Stop instance**).
2. Open **Target Groups → users-tg → Targets** and click refresh. After about 20 to 30 seconds the target changes to **unhealthy**.
3. Reload `http://<alb-dns>/users` in the browser several times. Every answer now comes from `users-2`, and you see no errors.
4. Start `users-1` again (**Instance state → Start instance**). Because the app is a systemd service, it comes back on boot, and the target returns to **healthy** after two successful checks.

Talking point: the client never noticed the failure. That is what the health check and the second instance bought us.

### Experiment B: a whole service fails

1. Stop **both** `orders` instances.
2. Open `http://<alb-dns>/orders` in the browser. It shows a **5xx** error page, usually **504 Gateway Time-out** (or 502 Bad Gateway). To see the exact code, open the browser developer tools (F12), go to the **Network** tab, and reload.
3. Open `http://<alb-dns>/users`. It still returns the JSON response.

Talking point: this is fault isolation, the main practical advantage of microservices. One service can go down while the other keeps working.

### Experiment C: no targets at all

1. In **Target Groups → orders-tg → Targets**, select both instances and choose **Deregister**.
2. Reload `http://<alb-dns>/orders`. The browser now shows **503 Service Temporarily Unavailable**.

Talking point: 503 means "nothing is registered to serve this". 504 means "targets exist but did not answer". Each tells an operator where to look.

### Experiment D: break the security group

1. Edit `app-sg` and delete the inbound rule from `alb-sg`.
2. Within about 30 seconds all targets become **unhealthy**, and requests fail with a 5xx.
3. Re-add the rule (**HTTP, source `alb-sg`**), and watch the targets recover.

Talking point: the instances are running and the app is fine. The failure is purely in the network path, and the health check status points straight to it.

### Experiment E: break the health check

1. Edit `users-tg`, and change the health check **port** to `8080` (override port).
2. Targets turn unhealthy even though the app answers on port 80.
3. Change the port back to **Traffic port**.

Talking point: "unhealthy" only means the check failed. Always compare the check's path, port, and success codes to what the app really serves.

### Discussion (10 minutes)

- What did the ALB give us that a single instance in a public subnet could not?
- What did we gain by splitting users and orders? What did we pay for it? (More instances, more rules, more networking, and harder debugging.)
- Why do the instances not need public IPs?
- When would a single monolith be the better choice? (Small team, simple app, low traffic.)
- How would the two services call each other? (An internal ALB, or service discovery.)

### Stretch goals

- Put each service in an **Auto Scaling group** with a launch template, and generate load to trigger scale-out.
- Add a **host-based rule** such as `users.example.com`, next to the path rules.
- Add an **HTTPS listener** with an ACM certificate, and redirect HTTP to HTTPS.
- Turn on **access logs** to S3 and find your own requests.

### Teardown and cost

An ALB is billed per hour while it exists, even with no traffic, so every student must delete it before leaving. Delete in this order, because each item depends on the next:

1. **The ALB** (this also removes its listener and rules).
2. **Both target groups.**
3. **The four instances** (terminate them).
4. **`app-sg`, then `alb-sg`.** `app-sg` references `alb-sg`, so `app-sg` goes first.

- [ ] ALB deleted, and the Load Balancers list is empty for your prefix.
- [ ] Instances show **Terminated**.
- [ ] Both security groups are gone.

Instructor tip: after class, search the console for any resource whose name starts with a student prefix, and check Load Balancers first.
