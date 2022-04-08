.SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := world

GBP_URL ?= http://gbp/
machine ?= gbp
build ?= 1

archive := build.tar.gz
container := $(machine)-root
chroot := buildah run --mount=type=tmpfs,tmpfs-mode=755,destination=/run $(container) --
config := $(notdir $(wildcard $(machine)/configs/*))
config_targets := $(config:=.copy_config)
repos_dir := /var/db/repos
repos := $(shell cat $(machine)/repos)
repos_targets := $(repos:=.add_repo)
stage4 := stage4.tar.xz

# Stage3 image tag to use.  See https://hub.docker.com/r/gentoo/stage3/tags
stage3-config := $(machine)/stage3


container: stage3-image := gentoo/stage3:$(shell cat $(stage3-config))
container: $(stage3-config)  ## Build the container
	-buildah rm $(container)
	buildah --name $(container) from --cap-add=CAP_SYS_PTRACE $(stage3-image)
	buildah config --env FEATURES="-cgroup -ipc-sandbox -mount-sandbox -network-sandbox -pid-sandbox -userfetch -userpriv -usersandbox -usersync binpkg-multi-instance buildpkg noinfo unmerge-orphans" $(container)
	touch $@


# Watermark for this build
gbp.json: world
	./gbp-meta.py $(machine) $(build) > $@


%.add_repo: %-repo.tar.gz container
	buildah unshare --mount CHROOT=$(container) sh -c 'rm -rf $$CHROOT$(repos_dir)/$*'
	buildah add $(container) $(CURDIR)/$< $(repos_dir)/$*
	touch $@


.SECONDEXPANSION:
%.copy_config: dirname = $(subst -,/,$*)
%.copy_config: files = $(shell find $(machine)/configs/$* ! -type l -print)
%.copy_config: $$(files) container
	buildah unshare --mount CHROOT=$(container) sh -c 'rm -rf $$CHROOT/$(dirname)'
	buildah copy $(container) "$(CURDIR)"/$(machine)/configs/$* /$(dirname)
	touch $@


chroot: $(repos_targets) $(config_targets)  ## Build the chroot in the container
	touch $@


world: chroot  ## Update @world and remove unneeded pkgs & binpkgs
	$(chroot) make -f- world < Makefile.container
	touch $@


packages: world
	buildah unshare --mount CHROOT=$(container) sh -c 'touch -r $${CHROOT}/var/cache/binpkgs/Packages $@'


container.img: packages
	buildah commit $(container) $(machine):$(build)
	rm -f $@
	buildah push $(machine):$(build) docker-archive:"$(CURDIR)"/$@:$(machine):$(build)


.PHONY: archive
archive: $(archive)  ## Create the build artifact


$(archive): gbp.json
	tar cvf build.tar --files-from /dev/null
	tar --append -f build.tar -C $(machine)/configs .
	buildah copy $(container) gbp.json /var/db/repos/gbp.json
	buildah unshare --mount CHROOT=$(container) sh -c 'tar --append -f build.tar -C $${CHROOT}/var/db repos'
	buildah unshare --mount CHROOT=$(container) sh -c 'tar --append -f build.tar -C $${CHROOT}/var/cache binpkgs'
	rm -f $@
	gzip build.tar


logs.tar.gz: chroot
	tar cvf logs.tar --files-from /dev/null
	buildah unshare --mount CHROOT=$(container) sh -c 'test -d $${CHROOT}/var/tmp/portage && cd $${CHROOT}/var/tmp/portage && find . -name build.log | tar --append -f $(CURDIR)/logs.tar -T-'
	rm -f $@
	gzip logs.tar


emerge-info.txt: chroot
	$(chroot) make -f- emerge-info < Makefile.container > .$@
	mv .$@ $@


push: packages  ## Push artifact (to GBP)
	$(MAKE) machine=$(machine) build=$(build) $(archive)
	gbp --url=$(GBP_URL) pull $(machine) $(build)
	touch $@


.PHONY: %.machine
%.machine: base ?= base
%.machine:
	@if test ! -d $(base); then echo "$(base) machine does not exist!" > /dev/stderr; false; fi
	@if test -d $*; then echo "$* machine already exists!" > /dev/stderr; false; fi
	@if test -e $*; then echo "A file named $* already exists!" > /dev/stderr; false; fi
	cp -r $(base)/. $*/


$(stage4): stage4.excl packages
	buildah unshare --mount CHROOT=$(container) sh -c 'tar -cf $@ -I "xz -9 -T0" -X $< --xattrs --numeric-owner -C $${CHROOT} .'


.PHONY: stage4
stage4: $(stage4)  ## Build the stage4 tarball

machine-list:  ## Display the list of machines
	@for i in *; do test -d $$i/configs && echo $$i; done; true


.PHONY: clean-container
clean-container:  ## Remove the container
	-buildah delete $(container)
	rm -f container


.PHONY: clean
clean: clean-container  ## Clean project files
	rm -rf build.tar $(archive) container container.img packages world *.add_repo chroot *.copy_config $(stage4) gbp.json push


.PHONY: help
help:  ## Show help for this Makefile
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
