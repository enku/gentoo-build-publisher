<div align="center">

# Gentoo Build Publisher Install Guide

</div>

This document provides step-by-step instructions on how to install [Gentoo
Build Publisher](https://github.com/enku/gentoo-build-publisher) (GBP).  This
document presumes a little familiarity with Gentoo, or else why would you be
reading it :wink:.  You should at least be familiar with the [Gentoo
Handbook](https://wiki.gentoo.org/wiki/Handbook:Main_Page).

This documents how to install Gentoo Build Publisher (GBP) on a single Gentoo
virtual machine (or physical machine or perhaps `systemd-nspawn` container).
There are other ways of installing Gentoo Build Publisher (bare metal,
containers, multiple machines, distros other than Gentoo, etc.) however
installing on a single virtual machine is the easiest to document.

## Table of Contents
- [Install Gentoo on a virtual machine](#install-gentoo-on-a-virtual-machine)
- [Install Required Packages](install-required-packages)
- [Configure Jenkins](#configure-jenkins)
- [Configure PostgreSQL](#configure-postgresql)
- [Create user for GBP](#create-user-for-gbp)
- [Install Gentoo Build Publisher](#install-gentoo-build-publisher)
- [Install the gbp CLI](#install-the-gbp-cli)
- [Configure nginx](#configure-nginx)
- [Configure rsyncd](#configure-rsyncd)
- [Start services](#start-services)
- [Create Jenkins jobs](#create-jenkins-jobs)
- [Get repos and binpkgs from the GBP instance](#get-repos-and-binpkgs-from-the-gbp-instance)


## Install Gentoo on a virtual machine.

The first step is to install Gentoo on a virtual machine.  There is nothing
special about doing this for GBP. Either testing or stable branches should
suffice. From now on we assume it's being installed on an amd64-based virtual
machine, but other hardware types may work as well.  A typical Handbook-style
installation should suffice.

Your virtual machines should be connected to a network which is accessible
from all the machines it will publish for.


### On Resource Requirements

As the primary purpose of GBP is to store lots of files, the GBP instance
should have adequate storage.  How much is needed depends on the usual "how
much space do I need for Gentoo" factors, as well as how many machine types it
will be hosting and how often builds are made.  For reference a by the (this)
book GBP instance with a single build from a single machine takes up about
9.1G of storage on the root filesystem.  By contrast, my "real" GBP instance,
which currently hosts 340 builds from 20 different machine types set me back
133G on (the equivalent of) `/home/gbp/`.  However read
[here](https://lunarcowboy.com/exploring-the-gentoo-build-publisher-dashboard.html)
about how GBP stores multiple builds of a machine efficiently.

As for how much RAM your instance needs that all depends on what packages are
being built, how many parallel builds, threads, etc.  Also if Jenkins is
configured for 4 workers and they're building 4 machines at the same time,
multiply that by 4.  A single-machine instance however should need no more
memory than building locally on the target machine.

### This Installation Document Requires systemd

I've thought about documenting installation using OpenRC since there is a bit
of...  politics regarding systemd. But the truth of the matter is all of my
systems are running on systemd, and I just don't have the time/interest to
figure out how to get it working on OpenRC or other init systems. However if
you know how to get GBP up and running with your favorite init system then
feel free to add to this document via a pull request.  Note that Gentoo Build
Publisher supports machine builds using any Gentoo-supported init system, not
just systemd.

## Install required packages

Install the required Gentoo packages:

```sh
# unmask jenkins-bin if in the stable tree
echo dev-util/jenkins-bin > /etc/portage/package.accept_keywords/jenkins-bin
echo app-misc/mime-types nginx > /etc/portage/package.use/gentoo-bin-publisher
echo net-firewall/iptables nftables >> /etc/portage/package.use/gentoo-bin-publisher
emerge --verbose --ask --noreplace \
    app-admin/sudo \
    app-containers/buildah \
    app-containers/runc \
    dev-db/postgresql \
    dev-lang/python:3.12 \
    dev-util/jenkins-bin \
    dev-vcs/git \
    net-misc/rabbitmq-server \
    net-misc/rsync \
    www-servers/nginx
```

## Configure Jenkins

Give the Jenkins user subordinate uids and gids for using rootless containers.

```sh
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 jenkins
```

Allow Jenkins to have lingering processes in systemd.

```sh
loginctl enable-linger jenkins
```

Start the Jenkins service.

```sh
systemctl enable --now jenkins
```


Note the initial password stored in
`/var/lib/jenkins/home/secrets/initialAdminPassword`. Point a web browser at
port 8080 of your virtual machine, e.g.  http://10.10.100.12:8080/ and enter
the password given in the file.

After entering the password, select the button to "Install suggested plugins".
Continue through the wizard filling out the forms.  When finished click the
"Start using Jenkins" button.

### Create a Jenkins API key

From the top bar in the Jenkins UI, click on your user/name. Then from the left
menu click "Configure".  Under "API Token" click the "Add new Token" button.
Give it the name "gbp" then click "Generate". "Copy the token now, because it
cannot be recovered in the future."  Click the "Save" button.

## Configure PostgreSQL

Configure PostgreSQL and start the service.

```sh
emerge --config postgresql
systemctl enable --now postgresql-16.service
```

> **_NOTE:_**  If a version of PostgreSQL other than 16 was installed,
> replace the `16` the major version number that was installed.

Create the role for gbp.

```sh
psql -U postgres -d template1 -c "CREATE USER gbp CREATEDB;"
```

Create the gbp database.

```sh
psql -U postgres -d template1 -c "CREATE DATABASE gbp OWNER gbp;"
```

## Create user for GBP

Create a user under which the GBP-specific services will run.

```sh
useradd -c "Gentoo Build Publisher" gbp
passwd --lock gbp
```

## Install Gentoo Build Publisher

Install the Python packages in the `gbp` user's home directory.

```sh
cd /home/gbp
sudo -u gbp -H git clone https://github.com/enku/gentoo-build-publisher.git
sudo -u gbp -H python3.12 -m venv .
sudo -u gbp -H ./bin/pip install -e ./gentoo-build-publisher gunicorn psycopg
mkdir -p /usr/local/bin
ln -s /home/gbp/bin/gbp /usr/local/bin/gbp
```

### Create the Django project

As GBP is a [Django](https://www.djangoproject.com/) app, it requires a Django project
to run.

```sh
sudo -u gbp -H ./bin/django-admin startproject \
    --template=./lib/python3.12/site-packages/gentoo_build_publisher/contrib/deployment/project_template \
    djangoproject .
```

### Create the configuration file

Copy the file `gentoo-build-publisher.conf` file over from the repo.

```sh
cp /home/gbp/lib/python3.12/site-packages/gentoo_build_publisher/contrib/deployment/gentoo-build-publisher.conf /etc/gentoo-build-publisher.conf
chown gbp:gbp /etc/gentoo-build-publisher.conf
chmod 0600 /etc/gentoo-build-publisher.conf
```

Open `/etc/gentoo-build-publisher.conf` with a text editor. Change
`BUILD_PUBLISHER_JENKINS_USER` value to the username you created in Jenkins
and the `BUILD_PUBLISHER_JENKINS_API_KEY` value to the API key you copied when
configuring Jenkins.  You did remember to copy that API key, right?

### Install systemd unit files

The gbp service requires a web app service and worker service.  Systemd unit
files exist for these in the gentoo-build-publisher repo.

```sh
mkdir -p /usr/local/lib/systemd/system
cp /home/gbp/lib/python3.12/site-packages/gentoo_build_publisher/contrib/deployment/*.service /usr/local/lib/systemd/system
systemctl daemon-reload
```

## Configure nginx

Copy the `contrib/deployment/nginx.conf` nginx configuration file.

```sh
cp /home/gbp/lib/python3.12/site-packages/gentoo_build_publisher/contrib/deployment/nginx.conf /etc/nginx/nginx.conf
```

Edit `/etc/nginx/nginx.conf` if needed, though the included one is sufficient
for most cases.

## Configure rsyncd

```sh
cp /home/gbp/lib/python3.12/site-packages/gentoo_build_publisher/contrib/deployment/rsyncd.conf /etc/rsyncd.conf
```


## Start services

Enable and start all the related services:

```sh
systemctl enable --now rabbitmq gentoo-build-publisher-wsgi gentoo-build-publisher-worker rsyncd nginx
```

## Create Jenkins jobs

Let's go back to Jenkins.


### Create a job for the Gentoo repo

Tell Gentoo Build Publisher to create a ebuild repo job from the official
Gentoo repo.

```sh
gbp addrepo gentoo https://anongit.gentoo.org/git/repo/gentoo.git
```

Now that we have a Gentoo repo job. Let's give it a whirl.  From the Jenkins
web interface, navigate to the "Gentoo" folder and then the "repos" folder.
Click on the "gentoo" item.  This is your Gentoo ebuild repository build.
Click on the "Build Now" link on the left.  The job should start running,
pulling (cloning, since it's the first time), the official Gentoo repo and
then creating an artifact. This artifact can then be used for machine builds.
This job will run periodically, polling the git repository and building new
artifacts.


### Create your first machine job

Now let's tell Gentoo Build Publisher to create a machine job.

```sh
gbp addmachine base https://github.com/enku/gbp-machines.git
```

Now that we have a machine build job, let's give it a whirl.  Ordinarily this
job will trigger automatically after successful repo builds. However we can
trigger a build manually from the shell:

```sh
gbp build base
```

After a few moments, if all goes successfully, you should have your first
completed build pushed to GBP.  Go to the GBP dashboard in a browser (The
hostname/IP of your virtual machine at port 80).

Congratulations! You have your first GBP machine build.  Let's tag it for
prosperity!

```sh
gbp tag base first
```

Now we should be able to publish the build which will make it available to
install.

```sh
gbp publish base
```


### Create subsequent machine jobs

Now let's create a build for the GBP instance itself.  There already exists a
build definition in the [`gbp-machines`](https://github.com/enku/gbp-machines)
git repo.

```sh
gbp addmachine gbpbox https://github.com/enku/gbp-machines.git
```

```sh
gbp build gbpbox
```

This creates and builds a machine that represents the GBP instance.  After the
build has completed, you can now use it to upgrade your GBP instance.  Publish
the (latest) build.

```sh
gbp publish gbpbox
```

## Get repos and binpkgs from the GBP instance

Now that we have a gbpbox build on gbpbox, we can use it to update itself.

```
cd /etc/portage
mv repos.conf repos.conf.bak
[ -e binrepos.conf ] && mv binrepos.conf binrepos.conf.bak
wget http://localhost/machines/gbpbox/repos.conf
wget http://localhost/machines/gbpbox/binrepos.conf
```

Sync and update from the GBP instance.

```
emerge --sync --quiet
emerge --deep --update --verbose --ask --newuse --getbinpkg @world
```

## The Dashboard and CLI

There is a dashboard for [showing a visual
representation](https://raw.githubusercontent.com/enku/gentoo-build-publisher/master/docs/media/dashboard.png)
of your Gentoo Build Publisher (less the Jenkins parts). Point your web
browser to the GBP instance on port 80, e.g. http://10.10.100.12/.

In addition the `gbp` [command line
interface](https://github.com/enku/gbpcli#readme) has useful commands for
interacting with your GBP instance.  You can use it from the instance itself
or install it on a local machine via pip:

```sh
pip install gbpcli
```

Note that some CLI commands, for example `addmachine`, `addrepo` and `check`
are only available from the GBP server instance.
