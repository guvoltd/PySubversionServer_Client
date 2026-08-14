#!/bin/bash
#
# Below is the list of all commands required to set up a basic `svnserve`
# server on Ubuntu systems. This script is for reference; the application
# provides interactive helpers to perform these steps.

# Step 1: Update the package list and install Subversion
sudo apt-get update
sudo apt install -y subversion

# Step 2: Verify the installation
svn --version --quiet

# Step 3: Create a system user and group for Subversion
# The svnserve daemon should run as a non-root user for security.
sudo addgroup --system svnserver
sudo adduser --system --no-create-home --disabled-password --ingroup svnserver svn

# Step 4: Create a directory for your SVN repositories (e.g., /var/svn)
sudo mkdir -p /var/svn

# Step 5: Set the appropriate permissions for the repository root
sudo chown -R svn:svnserver /var/svn
sudo chmod -R 770 /var/svn

# Step 6: Create your first repository
sudo -u svn svnadmin create /var/svn/myproject

# Step 7: Configure the repository's access rules
# Edit /var/svn/myproject/conf/svnserve.conf, passwd, and authz.
# The SVN Server Admin application provides a GUI for this.

# Step 8: Start svnserve as a systemd service
# The SVN Server Admin application can generate and install this for you.
# A typical unit file (/etc/systemd/system/svnserve.service) looks like this:
#
# [Unit]
# Description=Subversion Repository Server
# After=network.target
#
# [Service]
# Type=simple
# ExecStart=/usr/bin/svnserve --daemon --foreground --root /var/svn
# Restart=on-failure
# User=svn
#
# [Install]
# WantedBy=multi-user.target
#
# After creating the file, run:
# sudo systemctl daemon-reload
# sudo systemctl enable --now svnserve
# sudo systemctl status svnserve
