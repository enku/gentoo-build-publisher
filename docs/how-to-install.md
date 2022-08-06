<div align="center">

# Gentoo Build Publisher Install Guide

</div>

This document provides step-by-step instructions on how to install [Gentoo
Build Publisher](https://github.com/enku/gentoo-build-publisher) (GBP).  This
document presumes a little familiarity with Gentoo, or else why would you be
reading it ;-).  You should at least be familiar with the [Gentoo
Handbook](https://wiki.gentoo.org/wiki/Handbook:Main_Page).

This documents how to install Gentoo Build Publisher (GBP) on a single Gentoo
virtual machine (or physical machine if you have one to spare).  There are
other ways of installing Gentoo Build Publisher (bare metal, containers,
multiple machines, distros other than Gentoo, etc.) however installing on a
single virtual machine is the easiest to document.

## Install Gentoo on a virtual machine.

The first step is to install Gentoo on a virtual machine.  There is nothing
special about doing this for GBP. Either testing or stable branches should
suffice. From now on we assume it's being installed on an amd64-based virtual
machine, but other hardware types may work as well.  A typical Handbook-style
installation should suffice.

Your virtual machines should be connected to a network which is accessible
from all the machines it will publish for.


## On resource requirements

As the primary purpose of GBP is to store lots of files, the GBP instance
should have adequate storage.  How much is needed depends on the usuall "how
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
feel free to add to this document via a pull request.

## Install required packages

Install the required Gentoo packages:

```sh
# unmask jenkins-bin if in the stable tree
echo dev-util/jenkins-bin >> /etc/portage/package.accept_keywords/gbp
emerge --verbose --ask --noreplace \
    app-admin/sudo \
    app-containers/buildah \
    app-containers/runc \
    dev-db/postgresql \
    dev-lang/python:3.10 \
    dev-util/jenkins-bin \
    dev-vcs/git \
    net-misc/rabbitmq-server \
    net-misc/rsync \
    www-servers/nginx
```

### Optional packages

Optional: install [pigz](https://zlib.net/pigz/) for a speedier gzip on
multi-core systems.

```sh
echo app-arch/pigz symlink >> /etc/portage/package.use/gbp
emerge --verbose --ask app-arch/pigz
```

## Configure Jenkins

Give the Jenkins user subordinate uids and gids for using rootless containers.

```sh
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 jenkins
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

Click on "Manage Jenkins", "Manage Plugins".  Click on the "Available" tab and
enter "CopyArtifact". Select the CopyArtifact plugin and click "Install
without restart".

### Create a Jenkins API key

From the top bar in the Jenkins UI, click on your user/name. Then from the left
menu click "Configure".  Under "API Token" click the "Add new Token" button.
Give it the name "gbp" then click "Generate". "Copy the token now, because it
cannot be recovered in the future."  Click the "Save" button.

## Configure PostgreSQL

Configure PostgreSQL and start the service.

```sh
emerge --config postgresql
systemctl enable --now postgresql-14.service
```

> **_NOTE:_**  If a version of PostgreSQL other than 14 was installed,
> replace the `14` the major version number that was installed.

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
sudo -u gbp -H python3.10 -m venv .
sudo -u gbp -H ./bin/pip install -e ./gentoo-build-publisher
sudo -u gbp -H ./bin/pip install gunicorn psycopg2
```

### Create the Django project

As GBP is a [Django](https://www.djangoproject.com/) app, it requires a Django project
to run.

```sh
sudo -u gbp -H ./bin/django-admin startproject djangoproject .
```

Now make some changes to the project's settings file.

```sh
$EDITOR djangoproject/settings.py
```

For the `ALLOWED_HOST` setting, use either the virtual machine's (static) IP
address or the hostname you'll be using to access the system from a web
browser plus `'localhost'`.  For example:

```python
ALLOWED_HOSTS = ['10.10.100.12', 'localhost']
```

or

```python
ALLOWED_HOSTS = ['gbpbox', 'localhost']
```

If you are unsure yet how it will be accessed via HTTP(s), use the wildcard,
`'*'` for now:

```python
ALLOWED_HOSTS = ['*']
```

Add the following to the list of `INSTALLED_APPS`:

    * 'ariadne_django'
    * 'gentoo_build_publisher'

Change the value of `ROOT_URLCONF` to `'gentoo_build_publisher.urls'`.

Change the `DATABASES` setting to the following:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'gbp',
        'HOST': 'localhost',
        'USER': 'gbp',
        'CONN_MAX_AGE': None,
    }
}
```

Add the following to the end of the `settings.py` and save:

```python
CELERY_BROKER_URL = 'pyamqp://guest@127.0.0.1//'
CELERY_BROKER_POOL_LIMIT = 0
STATIC_ROOT = '/home/gbp/share/static_media'
```

### Create [Celery](http://celeryproject.org/) app

Create a the file `/home/gbp/djangoproject/celery.py`. There is already a copy
in the gentoo-build-publisher repo.

```sh
cp /home/gbp/gentoo-build-publisher/contrib/deployment/celery.py /home/gbp/djangoproject/celery.py
chown gbp:gbp /home/gbp/djangoproject/celery.py
```

### Create the configuration file

Copy the file `gentoo-build-publisher.conf` file over from the repo.

```sh
cp /home/gbp/gentoo-build-publisher/contrib/deployment/gentoo-build-publisher.conf /etc/gentoo-build-publisher.conf
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
cp /home/gbp/gentoo-build-publisher/contrib/deployment/*.service /usr/local/lib/systemd/system
systemctl daemon-reload
```

## Install the gbp CLI

> **_NOTE:_**  This is a temporary method until
> [`gbpcli`](https://github.com/enku/gbpcli) is packaged.

Install the [`shiv`](https://shiv.readthedocs.io/en/latest/) package.

```sh
sudo -u gbp -H /home/gbp/bin/pip install shiv
```

Use shiv to create a `gbp` "binary".

```sh
/home/gbp/bin/shiv -o /usr/local/bin/gbp -e gbpcli:main git+https://github.com/enku/gbpcli
```

## Configure nginx

Copy the `contrib/deployment/nginx.conf` nginx configuration file.

```sh
cp /home/gbp/gentoo-build-publisher/contrib/deployment/nginx.conf /etc/nginx/nginx.conf
```

Edit `/etc/nginx/nginx.conf` if needed.

## Configure rsyncd

```sh
cp /home/gbp/gentoo-build-publisher/contrib/deployment/rsyncd.conf /etc/rsyncd.conf
systemctl enable --now rsyncd
```


## Start services

Enable and start all the related services:

```sh
systemctl enable --now rabbitmq
systemctl enable --now gentoo-build-publisher-wsgi
systemctl enable --now gentoo-build-publisher-worker
```

## Create Jenkins jobs

Let's go back to Jenkins.

Configure [buildah](https://buildah.io/).

```sh
sudo -u jenkins -H mkdir -p /var/lib/jenkins/.config/containers
sudo -u jenkins -H cp /home/gbp/gentoo-build-publisher/contrib/deployment/containers.conf /var/lib/jenkins/.config/containers/containers.conf
```

Go back to your virtual machine in a browser on port 8080.

I prefer having all my Gentoo items in a separate Jenkins folder.  From the Dashboard
click the "New Item" link in the upper left. Give it the name "Gentoo", click the
"Folder" type and confirm. On the next page, click "Save".

### Create a job for the Gentoo repo

In the Jenkins UI, under the Gentoo folder create another folder called "repos".  Under
the repos folder create a new item.  Call it "gentoo" (lower case "g").  Make it of type
"Freestyle project" and confirm. In the next page, configure the "gentoo" project.
Select "git" for Source Code Management. For the repository URL enter
"https://anongit.gentoo.org/git/repo/gentoo.git". Under "Additional Behaviors" add
"Advanced clone behaviours", then click on the "Shallow clone" checkbox. For Build
Triggers set it to build periodically on a schedule of once per day ("@daily"). For
Build Steps add an "Execute Shell" step with the following script content:

```sh
artifact="${JOB_BASE_NAME}"-repo.tar.gz
date -R -u > ./metadata/timestamp.chk
python -c 'import json, os, sys; json.dump({"source": os.environ["GIT_URL"], "commit": os.environ["GIT_COMMIT"], "build": int(os.environ["BUILD_ID"])}, sys.stdout)' > ./metadata/build.json
rm -f "${artifact}"
mkdir -p "${WORKSPACE_TMP}"
tar cf "${WORKSPACE_TMP}"/"${artifact}" -I 'gzip -9' --exclude-vcs --exclude-vcs-ignores .
mv "${WORKSPACE_TMP}"/"${artifact}" .
```

For Post-build Actions add "Archive the artifacts".  Enter "\*-repo.tar.gz"
for Files to archive.

Click Save.

Now that we have a Gentoo repo job. Let's give it a whirl.  Click on the
"Build Now" link on the left.  The job should start running, pulling (cloning,
since it's the first time), the official Gentoo repo and then creating an
artifact.  This artifact can then be used for machine builds.


### Create a machine job

In the Jenkins UI navigate over to the "Dashboard > Gentoo" folder. Click on
"New Item". For the name call it "base".  For type choose "Pipeline" and
confirm.  Click on "Do not allow concurrent builds".  Under "Build Triggers",
click on "Build after other projects are built".  For "Projects to watch"
enter "repos/gentoo".  Under "Pipeline" select "Pipleline script from SCM"
from the dropdown.  For "SCM" select "Git". Under "Repository URL" enter
"https://github.com/enku/gbp-machines.git".  Click "Save".

Now that we have a machine build job, let's give it a whirl.  From the shell
promt:

```
gbp build base
```

After a few moments, if all goes successfully, you should have your first
completed build pushed to GBP.  Go to the GBP dashboard in a browser (The
hostname/IP of your virtual machine at port 80).

Now we should be able to publish the build which will make it available to
install.

```sh
gbp publish base
```
