# Gentoo Build Publisher Artifact Specification

The purpose of this document is to describe what goes into a Gentoo Build
Publisher artifact. An artifact is the compressed `tar` archive built (by
Jenkins) and pulled to Gentoo Build Publisher for publishing. The default name
for a GBP artifact is `build.tar.gz`.

This is a rather short document because the artifact is a simple structure.

## Content Types

After GBP pulls an artifact it unpacks it and looks for 4 items in the root of
the archive. The Gentoo Build Publisher term for this is "content types". Each
content type **must** exist in the artifact.  They are:

* `binpkgs` The `binpkgs` directory contains the contents of the `PKGDIR` for
  the given build.  The default location is `/var/cache/binpkgs`.
* `etc-portage` is the copy of the `/etc/portage` directory used by the
  container to build the artifact.
* `repos` The repos directory contains the contents of `PORTDIR` for the given
  build. The default location is `/var/db/repos`. In a default configuration
  there will be a `gentoo` subdirectory containing a copy of the official
  Gentoo ebuild repo. There may be additional subdirectories if overlays are
  used.
* `var-lib-portage` is the copy of the `/var/lib/portage` directory use by the
  container to build the artifact. Most importantly this typically contains
  the `world` file.

## Reference

See the reference GBP build mechanism,
[gbp-machines](https://github.com/enku/gbp-machines), specifically the
[Makefile](https://github.com/enku/gbp-machines/blob/master/Makefile), which
does something similar to:

```sh
tar cvf build.tar --files-from /dev/null
tar --append -f build.tar -C $(machine)/configs .
buildah unshare --mount CHROOT=$container sh -c 'tar --append -f build.tar -C $CHROOT/var/db repos'
buildah unshare --mount CHROOT=$container sh -c 'tar --append -f build.tar -C $CHROOT/var/cache binpkgs'
gzip build.tar
```
