# AWS VPC Lab — Public/Private Subnets, IGW, NAT, and Availability Zones

## Assignment overview

You will build a VPC with a public subnet (internet via an Internet Gateway) and a private subnet (outbound-only via a NAT Gateway), reach the private instance through a bastion host, and prove every result with AWS console and terminal screenshots in a submitted report.

## Submission requirements

Submit one report containing every required screenshot (labelled SS-01 to SS-29 below), a caption for each, and written answers to every question marked **Q**.

### Report format

- File: PDF or Word, named `VPC-Lab_<LastName>_<StudentID>`.
- Answers to **Q** questions: 2-5 sentences each, in your own words.

### Required screenshot checklist

Use this list to check your report before submitting.

| ID | Part | What it must show |
| --- | --- | --- |
| SS-01 | Build, Step 1 | `lab-vpc` with CIDR 10.0.0.0/16, DNS hostnames and DNS resolution enabled |
| SS-02 | Build, Step 2 | Subnet list showing `public-a` and `private-a` with CIDRs and AZ |
| SS-03 | Build, Step 2 | `public-a` settings with auto-assign public IPv4 enabled |
| SS-04 | Build, Step 3 | `lab-igw` in state Attached to `lab-vpc` |
| SS-05 | Build, Step 4 | `public-rt` Routes tab (0.0.0.0/0 → igw) |
| SS-06 | Build, Step 4 | `public-rt` Subnet associations tab (`public-a`) |
| SS-07 | Build, Step 5 | `lab-nat` status Available, subnet `public-a`, Elastic IP shown |
| SS-08 | Build, Step 6 | `private-rt` Routes tab (0.0.0.0/0 → nat) |
| SS-09 | Build, Step 6 | `private-rt` Subnet associations tab (`private-a`) |
| SS-10 | Build, Step 7 | `bastion-sg` inbound rules |
| SS-11 | Build, Step 7 | `private-sg` inbound rules (source = `bastion-sg`) |
| SS-12 | Build, Step 8 | Instances list: both running, with public/private IPs and subnets visible |
| SS-13 | Build, Step 8 | `private-app` details showing no public IPv4 address |
| SS-14 | Test 1 | Terminal: successful SSH to `private-app` via `-J` |
| SS-15 | Test 2 | Terminal on private instance: `curl -s ifconfig.me` output |
| SS-16 | Test 2 | Console: Elastic IPs page showing the same IP as SS-15 |
| SS-17 | Test 2 | Terminal: `sudo dnf check-update` succeeding |
| SS-18 | Test 3 | Terminal on your laptop: direct SSH to private IP timing out |
| SS-19 | Test 4 | Terminal on bastion: `curl ifconfig.me` returning the bastion public IP |
| SS-20 | Test 4 | Console: bastion details showing the same public IP as SS-19 |
| SS-21 to SS-24 | Break it | For each of the 4 experiments: the console change **and** the resulting failure (two images per experiment are fine, label them SS-21a/SS-21b etc.) |
| SS-25 | Break it | Console showing every change reverted and a working test afterwards |
| SS-26 | Final result | Resource map of `lab-vpc` (VPC → Your VPCs → select → Resource map tab) |
| SS-27 | Final result | VPC dashboard summary showing counts of VPCs, subnets, route tables, IGWs, NAT gateways |
| SS-28 | Cleanup | NAT Gateway state Deleted and Elastic IPs list empty |
| SS-29 | Cleanup | Your VPCs list without `lab-vpc` and EC2 instances all Terminated |

## Part 1: Foundations: Regions and Availability Zones

A VPC spans a whole Region, but each subnet lives in exactly one Availability Zone; that rule decides where your resources physically run.

### Region

A Region is a separate geographic area where AWS runs infrastructure (e.g. `us-east-1` N. Virginia, `eu-west-1` Ireland). Regions are fully independent of each other: separate resources, separate pricing, separate failure domains.

### Availability Zone (AZ)

An Availability Zone is one or more physically separate data centers inside a Region, with independent power, cooling, and networking.

- Each Region has at least 3 AZs (most have 3-6), named like `us-east-1a`, `us-east-1b`, `us-east-1c`.
- AZs in a Region are connected by fast, low-latency private fiber (typically single-digit milliseconds), so you can replicate data between them synchronously.
- They are placed far enough apart that a fire, flood, or power failure in one is unlikely to affect another, but close enough for low latency.
- Purpose: high availability. If you spread your app across 2+ AZs, losing one data center doesn't take your application down.

```
Region: us-east-1
├── AZ us-east-1a  (data center(s) A)
├── AZ us-east-1b  (data center(s) B)
└── AZ us-east-1c  (data center(s) C)
      ▲ connected by low-latency private fiber ▲
```

### Good to know

- **AZ names are per-account.** Your `us-east-1a` may be a different physical AZ than someone else's `us-east-1a`. AWS shuffles the mapping to spread load. To identify the real AZ, use the AZ ID (e.g. `use1-az1`), shown in the EC2 console or via `aws ec2 describe-availability-zones`.
- **Local Zones and Wavelength Zones** are extensions of a Region closer to specific cities or 5G networks. Not needed for this lab.

### Which resources are tied to what?

| Scope | Resources |
| --- | --- |
| Region-wide | VPC (spans all AZs), Internet Gateway, route tables, security groups (VPC-level objects) |
| Single AZ | Subnet, NAT Gateway, EC2 instance, EBS volume |

**Q1.**  View the AZ list in the EC2 console. Record the AZ name and AZ ID you used for this lab

## Part 2: What each component is and why you need it

Traffic from the internet reaches only the public subnet through the IGW; the private subnet goes out through the NAT Gateway and cannot be reached from outside.

```
                     Internet
                        │
                     [ IGW ]
                        │
┌──┴──────────────── VPC 10.0.0.0/16 ──────────────────┐
│ Public subnet 10.0.1.0/24      Private subnet 10.0.2.0/24
│ ├─ Bastion (public IP)         ├─ App server (no public IP)
│ └─ NAT Gateway (EIP) ◄────────┘  0.0.0.0/0 → NAT
│ RT: 0.0.0.0/0 → IGW            RT: 0.0.0.0/0 → NAT
└───────────────────────────────────────────────────────┘
```

### VPC (Virtual Private Cloud)

- Your own isolated virtual network in a Region. Nothing gets in or out unless you configure it.
- You choose its IP range (CIDR), here `10.0.0.0/16`, giving 65,536 addresses. Allowed sizes are /16 to /28, and you should use private ranges (RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- Use it to separate environments (dev/prod) and control exactly what is exposed.

### Subnet

- A slice of the VPC's CIDR that lives in one Availability Zone.
- AWS reserves 5 IPs per subnet (first 4 and last 1), so a /24 has 251 usable addresses.
- "Public" or "private" is not a setting. A subnet is public only if its route table sends `0.0.0.0/0` to an Internet Gateway.

### Route table

- A list of rules saying where traffic for a destination CIDR goes. Every subnet is associated with exactly one.
- Every table has an automatic local route (`10.0.0.0/16 → local`) so all subnets in the VPC can talk to each other, across AZs.
- The most specific matching route wins. `0.0.0.0/0` is the catch-all "default route".
- The main route table applies to any subnet you haven't explicitly associated. Best practice: leave it untouched and create custom ones.

### Internet Gateway (IGW)

- A managed, highly available gateway that connects the VPC to the internet. One per VPC. It is Region-scoped, not tied to an AZ.
- Provides two-way access, but only for resources that have a public IPv4 address (it does the 1:1 translation between private and public IP).
- Use it for anything that must be reachable from the internet (load balancers, bastions, web servers).

### Elastic IP (EIP)

- A static public IPv4 address you own until you release it.
- The NAT Gateway needs one. A normal auto-assigned public IP is released when an instance stops, but an EIP persists.
- Public IPv4 addresses, including EIPs, are billed hourly, even unattached.

### NAT Gateway

- A managed service that lets private instances initiate outbound connections (OS updates, API calls) while blocking inbound connections from the internet.
- It sits in a public subnet because it needs the IGW to reach the internet. The private route table points to it.
- It is AZ-scoped. For production high availability, create one per AZ.
- Costs an hourly rate plus per-GB processing, so check current pricing for your Region.

### Security Group (SG)

- A virtual firewall attached to an instance's network interface.
- Stateful: if inbound traffic is allowed, the reply is automatically allowed.
- Allow rules only; everything is denied by default.
- Can reference another SG as a source (e.g. "SSH allowed from `bastion-sg`"), which is more robust than IP addresses.

### Bastion host (jump box)

- A hardened instance in the public subnet that is the only SSH entry point to private resources.
- Modern alternatives: AWS Systems Manager Session Manager or EC2 Instance Connect Endpoint, which need no public IP or open port 22.

### Key pair

- Public/private SSH keys used to log in to Linux instances. AWS stores the public half, and you download the `.pem` once.

**Q2.** In your own words, explain what makes a subnet "public". Why is ticking "auto-assign public IPv4" not enough on its own?

## Part 3: Build it

Complete steps 1-8 in order and capture screenshots SS-01 to SS-13 as you go; each step lists exactly what to capture.

**Prerequisites:** an AWS account, a Region (e.g. `us-east-1`), and a key pair named `lab-key` (EC2 → Key Pairs → Create, RSA, `.pem`).

### Step 1: Create the VPC

VPC → Create VPC → VPC only. Name `lab-vpc`, IPv4 CIDR `10.0.0.0/16`. Then Actions → Edit VPC settings → enable DNS hostnames (DNS resolution should already be on).

*Why:* DNS support lets instances resolve names, and hostnames give instances DNS names.

> 📸 **SS-01:** `lab-vpc` details page showing the CIDR, DNS hostnames = Enabled, DNS resolution = Enabled, and your `Owner` tag.

### Step 2: Create subnets

Create two subnets in `lab-vpc`, both in the same AZ for now (e.g. `us-east-1a`):

| Name | CIDR | AZ |
| --- | --- | --- |
| public-a | 10.0.1.0/24 | us-east-1a |
| private-a | 10.0.2.0/24 | us-east-1a |

Select `public-a` → Actions → Edit subnet settings → enable auto-assign public IPv4.

*Why:* Instances launched here get a public IP automatically, which the IGW needs to route them.

> 📸 **SS-02:** Subnets list filtered to `lab-vpc`, showing both subnets with CIDR, AZ and available IPv4 count.

> 📸 **SS-03:** `public-a` details showing Auto-assign public IPv4 address = Yes.

### Step 3: Internet Gateway

Create `lab-igw`, then Actions → Attach to VPC → `lab-vpc`.

*Note:* Creating it isn't enough. It does nothing until it is attached and routed.

> 📸 **SS-04:** Internet gateways list showing `lab-igw` with State = Attached and the VPC ID of `lab-vpc`.

### Step 4: Public route table

- Create `public-rt` in `lab-vpc`.
- Routes → Edit → add `0.0.0.0/0` → target Internet Gateway → `lab-igw`.
- Subnet associations → `public-a`.

This step is what makes `public-a` public.

> 📸 **SS-05:** `public-rt` Routes tab showing both the local route and `0.0.0.0/0 → igw-…`.

> 📸 **SS-06:** `public-rt` Subnet associations tab showing `public-a`.

### Step 5: NAT Gateway

- VPC → NAT gateways → Create.
- Name `lab-nat`, subnet `public-a`, connectivity Public.
- Click Allocate Elastic IP.
- Wait until status is Available (about 1-2 minutes).

> 📸 **SS-07:** `lab-nat` details showing State = Available, Subnet = `public-a`, and its Elastic IP / primary public IPv4 address. Write this IP down; you will compare it in Test 2.

### Step 6: Private route table

Create `private-rt`. Add `0.0.0.0/0` → NAT Gateway → `lab-nat`. Associate with `private-a`.

*Result:* Private instances send internet-bound traffic to the NAT, which forwards it out through the IGW using its EIP.

> 📸 **SS-08:** `private-rt` Routes tab showing `0.0.0.0/0 → nat-…`.

> 📸 **SS-09:** `private-rt` Subnet associations tab showing `private-a`.

### Step 7: Security groups

Create both in `lab-vpc`:

| SG | Inbound rule | Notes |
| --- | --- | --- |
| bastion-sg | SSH (22) from My IP | Leave default outbound (all) |
| private-sg | SSH (22), source = `bastion-sg` | Choose the SG, not an IP. Optionally add ICMP from `10.0.0.0/16` for ping tests |

> 📸 **SS-10:** `bastion-sg` Inbound rules tab (blur your IP if you wish, but keep `/32` visible).

> 📸 **SS-11:** `private-sg` Inbound rules tab showing the source is the `sg-…` ID of `bastion-sg`.

### Step 8: Launch instances

EC2 → Launch instance: Amazon Linux 2023, t3.micro, key pair `lab-key`.

- **Bastion:** name `bastion`, VPC `lab-vpc`, subnet `public-a`, auto-assign public IP Enable, SG `bastion-sg`.
- **Private:** name `private-app`, subnet `private-a`, auto-assign public IP Disable, SG `private-sg`.

> 📸 **SS-12:** EC2 Instances list showing both instances Running and 2/2 status checks passed, with Public IPv4 and Private IPv4 columns visible.

> 📸 **SS-13:** `private-app` Details tab showing Public IPv4 address = – (none) and its subnet.

**Q3.** The NAT Gateway is placed in `public-a`, not `private-a`. Explain why, referring to the route tables you built.

## Part 4: Test and verify

Four tests prove the design works: SSH reaches the private instance only through the bastion, and outbound traffic leaves through the NAT's Elastic IP. Capture SS-14 to SS-20.

### Test 1: SSH to the private instance through the bastion

From your computer:

```bash
chmod 400 lab-key.pem
ssh-add lab-key.pem
ssh -A -i lab-key.pem -J ec2-user@<BASTION_PUBLIC_IP> ec2-user@<PRIVATE_IP>
```

`-J` (ProxyJump) tunnels through the bastion without copying your key onto it.

> 📸 **SS-14:** Terminal showing the full `ssh` command and the Amazon Linux login banner, with the prompt showing the private IP hostname (e.g. `ip-10-0-2-x`). Run `hostname -I` after login so the private IP is visible.

### Test 2: Verify outbound via NAT

On the private instance:

```bash
curl -s ifconfig.me ; echo     # should print the NAT's Elastic IP
sudo dnf check-update          # package repos reachable
```

Compare the output to the EIP in VPC → Elastic IPs.

> 📸 **SS-15:** Terminal on `private-app` showing the `curl` command and the IP it returns.

> 📸 **SS-16:** VPC → Elastic IPs page showing the same address, associated with `lab-nat`.

> 📸 **SS-17:** Terminal on `private-app` showing `sudo dnf check-update` completing without a timeout.

### Test 3: Verify inbound is blocked

From your laptop, `ssh -i lab-key.pem ec2-user@<PRIVATE_IP>` times out, because the private IP isn't routable from the internet.

> 📸 **SS-18:** Laptop terminal showing the direct SSH attempt and the timeout error. Tip: add `-o ConnectTimeout=10` so it fails quickly.

### Test 4: Verify the bastion's own path

`curl ifconfig.me` on the bastion returns its own public IP, because it goes through the IGW directly rather than the NAT.

> 📸 **SS-19:** Terminal on `bastion` showing the `curl` output.

> 📸 **SS-20:** EC2 console details of `bastion` showing the same Public IPv4 address.

### Final result screenshots

With everything working, capture the finished network:

> 📸 **SS-26:** VPC → Your VPCs → `lab-vpc` → **Resource map** tab, showing subnets, route tables and network connections (IGW, NAT).

> 📸 **SS-27:** VPC dashboard ("Resources by Region") showing counts for your VPC, subnets, route tables, internet gateways, NAT gateways and Elastic IPs.

**Q4.** Tests 2 and 4 return different public IPs. Explain why, tracing each packet's path through the route tables.

**Q5.** Why is `ssh -J` safer than copying `lab-key.pem` onto the bastion?

## Part 5: Break it on purpose

Run each experiment, record the failure, then revert it before starting the next one; each experiment needs a screenshot of the change and one of the resulting failure (SS-21 to SS-24), plus SS-25 proving everything works again.

| # | Experiment | Expected result | Lesson | Screenshots |
| --- | --- | --- | --- | --- |
| 1 | Delete `0.0.0.0/0` from `private-rt` | `curl` hangs | NAT only works if routed | SS-21a: `private-rt` routes without the default route · SS-21b: `curl` timing out on `private-app` |
| 2 | Remove the IGW route from `public-rt` | Can't SSH to the bastion | Public = route to IGW | SS-22a: `public-rt` routes · SS-22b: SSH to bastion timing out |
| 3 | Change `private-sg` source to a wrong IP | Bastion SSH to private fails | SG rules are default-deny | SS-23a: edited `private-sg` rule · SS-23b: `ssh -J` failing |
| 4 | Stop and start the bastion | Its public IP changes | Why EIPs exist | SS-24a: bastion public IP before stop · SS-24b: new public IP after start |

> 📸 **SS-25:** After reverting all four changes, show `public-rt` and `private-rt` routes restored and a terminal with a successful `ssh -J` and `curl -s ifconfig.me` on `private-app`.

## Part 6: What if the subnets are in different AZs?

Nothing breaks. The lab works the same, because route tables and the local route span the whole VPC regardless of AZ. Your private instance can still reach the NAT, and your bastion can still SSH to the private instance.

What changes is cost and resilience:

- **Cross-AZ data charges:** Private traffic to a NAT in another AZ is billed as cross-AZ data transfer (around $0.01/GB each way, so check current pricing), on top of the NAT's own processing fee.
- **Small latency increase:** An extra hop between AZs, usually only a millisecond or so.
- **Lost fault isolation:** A NAT Gateway lives in one AZ. If that AZ goes down, private subnets in other AZs lose outbound internet too, even though they're healthy.

### Production best practice

One NAT per AZ, and one private route table per AZ:

```
public-a → NAT-a ◄── private-rt-a ── private-a
public-b → NAT-b ◄── private-rt-b ── private-b
```

Each private subnet routes to the NAT in its own AZ, so there are no cross-AZ fees and an AZ failure stays contained. The tradeoff is paying for multiple NAT Gateways, so for dev or lab setups a single NAT is a common cost-saving choice.

### Multi-AZ design at a glance

| Component | Multi-AZ approach |
| --- | --- |
| Subnets | One public + one private subnet per AZ |
| NAT Gateway | One per AZ |
| Route tables | One private route table per AZ (each pointing to its own AZ's NAT) |
| IGW | One for the whole VPC (already Region-wide and highly available) |
| EC2 / app tier | Spread instances across AZs (Auto Scaling Group + Load Balancer) |
| Databases | Multi-AZ deployment (e.g. RDS Multi-AZ) |

### Written questions

**Q7.** Your company runs private subnets in `us-east-1a` and `us-east-1b` with a single NAT Gateway in `us-east-1a`. Describe what happens to each subnet if `us-east-1a` fails, and propose a fix.

**Q8.** Draw (by hand or with any diagram tool) a two-AZ version of this lab: two public subnets, two private subnets, two NAT Gateways and the route tables. Include the diagram in your report with a CIDR for every subnet that fits inside `10.0.0.0/16` without overlapping.

**Q9.** A private instance in `us-east-1b` sends 500 GB per month through a NAT Gateway in `us-east-1a`. Using the current AWS pricing page for your Region, estimate the monthly cross-AZ and NAT processing charges, and compare with the cost of adding a second NAT Gateway. Cite the pricing page you used.

## Cleanup

Cleanup is graded: you must prove every billable resource is gone with SS-28 and SS-29.

Do it in this order to avoid dependency errors and charges:

1. Terminate both EC2 instances
2. Delete the NAT Gateway and wait until it shows *Deleted*
3. Release the Elastic IP
4. Detach and delete the IGW
5. Delete the subnets
6. Delete `public-rt` and `private-rt`
7. Delete the security groups
8. Delete the VPC

> ⚠️ **NAT Gateways and public IPv4 addresses bill by the hour.** Delete the NAT Gateway and release the EIP first, and don't leave them running after the lab.

> 📸 **SS-28:** NAT gateways list showing `lab-nat` State = Deleted, and the Elastic IPs page showing no addresses.

> 📸 **SS-29:** Your VPCs list without `lab-vpc` (only the default VPC, if any), and EC2 Instances showing both lab instances Terminated.

**Q10.** Why must the NAT Gateway be deleted before the Elastic IP can be released, and why must the IGW be detached before the VPC can be deleted?
