# Gentoo Build Publisher

## Introduction

Right now for all my [Gentoo](https://www.gentoo.org) systems (physical, VMs,
and containers) I have [Jenkins](https://www.jenkins.io) builds that creates
binary packages for them.  The actual builds are done in (systemd) containers.
The builds are triggered by periodically polling the Gentoo portage git repo,
related overlays and the machine's "build" repo itself.  The systemd containers
that build the packages have their binary packages exposed by a web service
container (gentoo build publisher) and the portage tree is exposed via rsync on
the host. When I want to update my system it's

```bash
# emerge --sync
# emerge --deep --upgrade --ask --newuse @world
```

The `/etc/portage` and `/var/lib/portage` directories for each system are also
kept in version control, which is tracked by Jenkins. So e.g. if I want to add
a package or change a use flag, I do so in the repo, push it and Jenkins picks
up the change and creates a new build job.

As Jenkins creates artifacts of all the successful builds those artifacts get
published to gentoo build publisher to host them.  This is done for both binary
packages and the portage tree. So when you sync/update from GBP you're always
getting a stable upgrade.  Even nicer, since successful all artifacts are kept
you can go back to a previous succesful build and still have the portage
snapshot and binary packages from that build.

Eventually I'd like to automate all this.  For example I want to stand up a new
system. I go to a web ui, give it a profile name and click "build". It creates
a new machine profile/repo pushes it and then creates a new job in Jenkins to
build from it. I can then build a new system from that.


## Procedure

I'm not going to go into all the details now as it's pretty complicated and may
change.  But basically the gist is this:

* You need a Jenkins instance
* Create a "portage" job in Jenkins.  This job should poll the portage git repo
  and publish and artifact (say `portage.tar.gz`) from it.
* Ditto for any overlays
* You need a chroot for Jenkins to build from for each machine type. I have a
  sudo script that Jenkins can call to build a chroot inside the job's
  workspace.
* For your machine type, say database, you create a Jenkins job. This job
  should pull in the artifacts from the last successfull portage build. It
  unpacks those into it's worspace.  You also need your machine's profile in a
  repo. That also gets built from Jenkins and the last successul build's
  archive pulled.  Unpack that as well in your Jenkins workspace.
* Your machine creates a `binpkgs` and `distfiles` directory (`mkdir -p`).
* Your database Jenkins job then uses `systemd-nspawn` into your chroot.  It
  should bind-mount /etc/portage, /var/lib/portage, overlays, distfiles, and
  binpkgs  inside the container.  Then it does a world update.  Upon success
  the job should pack the `repos` and `binpkgs` into a tar archive.
* Your job should have a post-build task that calls the Gentoo Build Publisher.
  It will then pull the specified archive and publish it (rsync for repos, http
  for binpkgs.
* If the job fails, it does not be published.
* Your real machine syncs from, e.g. rsync://gbp/repos/database/ and pulls binary
  packages from http://gbp/binpkgs/database/
