# Lab 2: Host the 2048 game on an EC2 instance

This week you launch an EC2 instance and serve a small web game from it. The game is a fork of 2048 at <https://github.com/halimo22/2048>. It replaces the Node.js website, which is too heavy for the AWS free tier.

The repo includes `install.sh`, which sets the game up after you clone it. It installs nginx (with `dnf`/`yum` on Amazon Linux or `apt-get` on Ubuntu), copies the game into nginx's web root and serves it on port 80.

## Steps

1. Create an EC2 instance.
2. Install git on the instance.
3. Clone the repo.
4. Run the bash script.
5. Allow HTTP on the instance through its security group.

For steps 2 to 4, on Amazon Linux:

```bash
sudo dnf install -y git          # on Ubuntu: sudo apt-get install -y git
git clone https://github.com/halimo22/2048.git
cd 2048
bash install.sh
```

When the security group allows inbound HTTP (port 80), open `http://<instance-public-ip>/` in your browser to play.

## What to submit

Send your instructor:

- The public IP address of your instance.
- Screenshots of the EC2 instance, its security group, and your terminal, with your name and ID visible.
