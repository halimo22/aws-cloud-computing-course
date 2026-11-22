# AWS Cloud Computing: Labs and Assignments

Hands-on labs for the AWS cloud computing course. Each lab builds on the one before it, from a single EC2 instance to containers running on ECS behind a load balancer. The full course outline is in the [12-week program](course-plan/12-week-program.pdf).

| Lab | Topic | What you do |
| --- | --- | --- |
| [Lab 2](lab-02-ec2-2048/) | EC2 and a first web app | Launch an EC2 instance, install the 2048 game with one script, open HTTP in the security group, and submit the IP and screenshots. |
| [Lab 3](lab-03-vpc-subnets-nat/) | VPC, subnets, Internet Gateway and NAT | Build a VPC with a public and a private subnet, an Internet Gateway, a NAT gateway and a bastion host; prove traffic flows the way the route tables say; break it on purpose; design the multi-AZ version. Submit one report with screenshots SS-01 to SS-29 and answers to Q1 to Q10. |
| [Lab 4](lab-04-security-groups-load-balancers/) | Security groups, load balancers and microservices | Put two services (users and orders) behind one Application Load Balancer with path-based routing, lock the instances down with security groups, then break the system on purpose and read the 502, 503 and 504 errors. Console only. |
| [Lab 5](lab-05-containers-ecr-ecs/) | IAM, containers, ECR and ECS | IAM users, roles and policies; what an artifact and a container image are; push an image to ECR and run it as an ECS Fargate service; configure it with environment variables. |
| [Lab 5 assignment](lab-05-containers-ecr-ecs/assignment.md) | VPC, EC2, Docker and ECS end to end | Build a VPC with public and private subnets, SSH through a bastion, add a NAT gateway, push the `halimo1/env-printer` image to ECR from CloudShell, and run it on ECS twice: on a public IP, and privately behind an ALB with VPC endpoints. Submit one PDF with screenshots S1 to S27 and the written answers. |

## Before you start

- You need an AWS account (or lab account) and the AWS Management Console. Lab 5 uses AWS CloudShell, so nothing is installed on your computer.
- Prefix every resource you create with your name or student ID, so shared accounts stay readable.
- Load balancers, NAT gateways and interface endpoints are billed by the hour. Do each lab's teardown section the same day.
