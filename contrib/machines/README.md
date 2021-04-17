# Gentoo Build Publisher: buildable machines

This is a (subset) of my "machines" git repo, which is not currently published
on github. It is the repo that each of my machine's Jenkins jobs pull from.
This example only includes the "gbp" machines.  The same
[Jenkinsfile](Jenkinsfile) and [Makefile](Makefile) are used for all machines
and the `Makefile` uses whichever machine config passed in as the `machine`
`Makefile` variable.  So, e.g., Jenkins calls it like:

```sh
$ make publish machine=gbp build=23
```

This is a work in progress. Eventually I'd like to have it also publish stage4
tarballs and container images.
