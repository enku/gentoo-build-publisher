<p align="center">
<img src="https://raw.githubusercontent.com/enku/gentoo-build-publisher/master/docs/media/dashboard.png" alt="Gentoo Build Publisher dashboard" width="100%">
</p>

# Gentoo Build Publisher

## Introduction

The idea is to combine best practices with [continuous
integration](https://en.wikipedia.org/wiki/Continuous_integration) and other
tools to deliver successful, consistent "builds" to your Gentoo machine(s).

In case you didn't know, [Gentoo Linux](https://www.gentoo.org/) is a
source-based rolling-release meta-distribution that you can twist and mold
into pretty much anything you like. That's just a verbose way of saying Gentoo
is awesome.

If you run a Gentoo system, say a laptop, you may be updating your system
using the standard `emerge --sync` followed by a world update.  This pulls in
the latest ebuilds from the Gentoo repo and if there are any updates
applicable to your system then they get built on your system.

Except sometimes they don't.

Sometimes builds fail. Sometimes `USE` flags need to be changed. Sometimes
there's an update to a piece of software that is buggy and you want to revert.
Sometimes a build takes a long time and you don't want to wait.

Well since Gentoo is the distribution you build yourself, CI/CD seems like a
natural fit. Enter Gentoo Build Publisher.

Gentoo Build Publisher is the combination of an rsync server (for ebuild repos
and machine configs) and HTTP server (for binpkgs) for successful builds.  For
Jenkins it is a gateway to publish builds. For my real machines it the source
for repo syncs and binpkgs.


## Procedure

* Build a Gentoo Build Publisher instance. Refer to the [Install
  Guide](https://github.com/enku/gentoo-build-publisher/blob/master/docs/how-to-install.md).
* Create "machines" and "repos" jobs in Jenkins.  Use [the following git
  repo](https://github.com/enku/gbp-machines) as a starting point.
* Once a Jenkins job has been pulled by Gentoo Build Publisher it can be
  published so that actual machines can use it (e.g. rsync for repos, http for
  binpkgs).  Use the CLI (`gbp publish`) to publish a pulled build.
* If the job fails, it will not be pulled.
* Your real machine, for example, `base`, syncs from, `rsync://gbp/repos/base/gentoo`.
  You can dynamically acquire the `repos.conf` file from
  `https://gbp/machines/base/repos.conf` and the `binrepos.conf` from
  `https://gbp/machines/base/binrepos.conf`.

<p align="center">
<img src="docs/media/gbp.svg" alt="Jenkins build" width="90%">
</p>

I have a git repo called `machines` that contains the profiles for all the
machines whose builds I want to push to the publisher.  You can fork the
[gbp-machines](https://github.com/enku/gbp-machines) repo as a starting point.

My Jenkins job does not publish a build by default. I (can) later publish the
build so that my machines can consume them.  There is a GraphQL interface for
doing such tasks as well as a [command-line
interface](https://github.com/enku/gbpcli).

# Software

This project hosts the application called gentoo-build-publisher. Combined
with Jenkins, the above procedure,`rsyncd`, a web server to serve binary
packages (e.g. nginx) and a [command-line interface](#cli) you can get all the
advantages of a source-based Linux distribution like Gentoo combined with the
advantages of binary distros plus even more.

# CLI

The [command-line interface](https://github.com/enku/gbpcli#readme) can
inspect, publish, pull, schedule builds and more.

# Articles

Below are some articles I've written that explain some aspects of Build
Publisher in detail.

- [Introducing Gentoo Build Publisher](https://lunarcowboy.com/introducing-gentoo-build-publisher.html): June 2021
- [Exploring the Gentoo Build Publisher Dashboard](https://lunarcowboy.com/exploring-the-gentoo-build-publisher-dashboard.html): November 2021
- [Getting failure logs](https://lunarcowboy.com/gentoo-build-publisher-getting-failure-logs.html): April 2022
- [Installing Gentoo Build Publisher](https://lunarcowboy.com/installing-gentoo-build-publisher.html) August 2022
- [Rolling Back a Rolling Release with Gentoo Build Publisher](https://lunarcowboy.com/rolling-back-a-rolling-release-with-gentoo-build-publisher.html): September 2022
