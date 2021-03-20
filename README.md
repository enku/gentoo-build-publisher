# Gentoo Build Publisher

## Introduction

Right now for all my [Gentoo](https://www.gentoo.org) systems (physical, VMs,
and containers) I have [Jenkins](https://www.jenkins.io) builds that creates
binary packages for them.  The actual builds are done in (systemd) containers.
The builds are triggered by periodically polling the Gentoo portage git repo.
I've run this setup for years and it runs well.  The systemd containers that
build the packages have their binary packages exposed by a web service
container and the portage tree is exposed via rsync on the host. When I want to
update my system it's

```bash
# emerge --sync
# emerge --deep --upgrade --ask --newuse @world
```

The `/etc/portage` directory and `world` for each system are also kept in
version control, which is tracked by Jenkins. So e.g. if I want to add a
package or change a use flag, I do so in the repo. Push it and via web hook
Jenkins picks up the change and creates a new job.

This all works relatively well but... what if the Jenkins build fails?  Well if
I do this when a Jenkins build is in a non-stable state then the respective
system is in a non-stable state.  So I have to wait until the next Jenkins
build passes in order to make my system(s) consistent.  That's the only part I
don't like.

Enter Gentoo Build Publisher. Instead of relying on the state of the build
containers, GBP is intented so, that Jenkins instead creates artifacts of all
the successful builds and those artifacts get published to a different server
that host them.  This is done for both binary packages and the portage tree. So
when you sync/update from GBP you're always getting a stable upgrade.  Even
nicer, since successful all artifacts are kept you can go back to a previous
succesful build and still have the portage snapshot and binary packages from
that build.

Eventually I'd like to automate all this.  For example I want to stand up a new
system. I go to a web ui, give it a profile name and click "build". It creates
a new profile in my etc_portage repo, pushes it, creates a new job in Jenkins
and starts the build. I can then build a new system from that.


## Procedure

I'm not going to go into all the details now as it's pretty complicated and may
change.  But basically the gist is this:

* You need a Jenkins instance
* Create a "portage" job in Jenkins.  This job should poll the portage git repo
  and publish and artifact (say `portage.tar.gz`) from it.
* Ditto for any overlays
* You need a chroot for Jenkins to build from for each machine type.
* For your machine type, say database, you create a Jenkins job. This job
  should pull in the artifacts from the last successfull portage build. It
  unpacks those into it's worspace.  You also need your machine's profile in a
  repo. That also gets built from Jenkins and the last successul build's
  archive pulled.  Unpack that as well in your Jenkins job.
* Your machine creates a `binpkgs` and `distfiles` directory (`mkdir -p`).
* Your database Jenkins job then uses `systemd-nspawn` into your chroot.  It
  should bind-mount portage, overlays, distfiles, and binpkgs  inside the
  container, It should bind mount your machine type's `/etc/portage` from your
  machine profile.  Ditto for the `world` file.  Then it does a world update.
  Upon success the job should pack the `repos` and `binpkgs` into a tar
  archive.
* Your job should have a post-build task that calls the Gentoo Build Publisher.
  It will then pull the specified archive and publish it (rsync for repos, http
  for binpkgs.
* If the job fails, it does not be published.
* Your real machine syncs from, e.g. rsync://gbp/repos/database/ and pulls binary
  packages from http://gbp/binpkgs/database/

Or at least that's the intention.
