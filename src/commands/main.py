import os
import shutil
import subprocess
from . import config as config_module
import click
import logging
import sys
import yaml
from os.path import exists, abspath
import tempfile


def read_dockerfile() -> str:
    """
    Reads and returns the contents of a Dockerfile used to compile
    the projects.
    """
    current_dir = os.path.dirname(os.path.realpath(__file__))
    dockerfile_path = os.path.join(current_dir, "dockerfiles", "Dockerfile.frr")
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        return f.read()


def read_demo_script() -> str:
    """
    Reads out the run-demo.sh file and returns it as a string.
    """
    current_dir = os.path.dirname(os.path.realpath(__file__))
    script_path = os.path.join(current_dir, "scripts", "run-demo.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        return f.read()


@click.group()
@click.option(
    "--config",
    type=click.Path(),
    show_default=True,
    default=config_module.DEFAULT_CONFIG,
    is_eager=True,
    help="Path to a configuration file.",
)
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
def test():
    print("hello")


@cli.group()
def config():
    pass


@config.command()
@click.option(
    "--upstream-url",
    type=str,
    help="Upstream repository to backport from. E.g., https://github.com/openshift/etcd.git",
)
@click.option(
    "--distgit-repo",
    type=str,
    help="The downstream distgit repository to backport to. E.g., https://src.fedoraproject.org/rpms/etcd.git",
)
@click.option(
    "--fixmorph-base-image",
    type=str,
    help="The base image to use for the fixmorph tool.",
    show_default=True,
)
@click.pass_context
def create(
    ctx,
    upstream_url: str | None,
    distgit_repo: str | None,
    fixmorph_base_image: str | None,
):
    configfile = ctx.obj["config"]
    # get these values from user
    if not distgit_repo:
        # TODO: resolve the default value from the filesystem
        distgit_repo = click.prompt(
            "Please enter the downstream dist-git repository URL (e.g. rpms/python)"
        )
    if not upstream_url:
        upstream_url = click.prompt(
            "Please enter the upstream repository URL (e.g. https://github.com/python/cpython.git)"
        )

    # ask if they want to provide a custom base image for fixmorph (optional)
    if not fixmorph_base_image:
        fixmorph_base_image = click.prompt(
            "Please enter the base image for fixmorph",
            default=config_module.DEFAULT_FIXMORPH_BASE_IMAGE,
        )

    # create a new config file
    config = config_module.BackporterConfig(
        fixmorph_base_image=fixmorph_base_image,
        upstream_url=upstream_url,
        distgit_repo=distgit_repo,
    )
    config.to_file(configfile)
    click.secho(f"Wrote config to {abspath(configfile)}", fg="green")


@config.command()
@click.option(
    "--upstream-url",
    type=str,
    help="Upstream repository to backport from. E.g., https://github.com/openshift/etcd.git",
)
@click.option(
    "--distgit-repo",
    type=str,
    help="The downstream distgit repository to backport to. E.g., https://src.fedoraproject.org/rpms/etcd.git",
)
@click.option(
    "--fixmorph-base-image",
    type=str,
    help="The base image to use for the fixmorph tool.",
    show_default=True,
)
@click.pass_context
def edit(
    ctx,
    upstream_url: str | None,
    distgit_repo: str | None,
    fixmorph_base_image: str | None,
):
    configfile = ctx.obj["config"]
    if not exists(configfile):
        click.secho(
            f"Config file {configfile} does not exist. Creating a new one.", fg="yellow"
        )
        create(upstream_url, distgit_repo, fixmorph_base_image)
        return

    # load config
    conf = config_module.read_config(configfile)

    distgit_repo = click.prompt(
        "Please enter the downstream dist-git repository URL", default=conf.distgit_repo
    )
    upstream_url = click.prompt(
        "Please enter the upstream repository URL", default=conf.upstream_url
    )
    fixmorph_base_image = click.prompt(
        "Please enter the base image for fixmorph", default=conf.fixmorph_base_image
    )

    # create a new config file
    new_config = config_module.BackporterConfig(
        fixmorph_base_image=fixmorph_base_image,
        upstream_url=upstream_url,
        distgit_repo=distgit_repo,
    )
    new_config.to_file(configfile)
    click.secho(f"Wrote config to {abspath(configfile)}", fg="green")


@config.command()
@click.pass_context
def view(ctx):
    configfile = ctx.obj["config"]
    if not exists(configfile):
        click.secho(f"Config file {configfile} does not exist.", fg="red")
        return

    # load config
    conf = config_module.read_config(configfile)
    click.secho(yaml.dump(conf.__dict__), fg="green")


# @cli.command(
#     help="Checks to make sure that the current machine has everything it needs."
# )
# @click.pass_context
# def check(ctx):
#     # check for commands
#     commands = ["git", "docker", "rhpkg"]
#     for cmd in commands:
#         if not shutil.which(cmd):
#             click.secho(f"Command '{cmd}' not found. Please install it.", fg="red")
#             return
#         click.secho(f"Found command: {cmd}", fg="green")

#     configfile = ctx.obj.get('config')
#     click.secho('Checking for configfile...')
#     if not configfile:
#         click.secho("No config file found. Please create one.", fg="red")
#         return


FRR_CONFIGURE = """./configure \
    --prefix=/usr \
    --includedir=\${prefix}/include \
    --bindir=\${prefix}/bin \
    --sbindir=\${prefix}/lib/frr \
    --libdir=\${prefix}/lib/frr \
    --libexecdir=\${prefix}/lib/frr \
    --sysconfdir=/etc \
    --localstatedir=/var \
    --with-moduledir=\${prefix}/lib/frr/modules \
    --enable-configfile-mask=0640 \
    --enable-logfile-mask=0640 \
    --enable-snmp=agentx \
    --enable-multipath=64 \
    --enable-user=frr \
    --enable-group=frr \
    --enable-vty-group=frrvty \
    --with-pkg-git-version \
    --with-pkg-extra-version=-MyOwnFRRVersion \
	--with-crypto=openssl
"""

FRR_BUILD = "make"


def Popen_stream(*args, **kwargs):
    click.secho(f"Running command: '{args}'", fg="green")
    click.secho(f"kwargs: '{kwargs}'", fg="green")
    try:
        proc = subprocess.Popen(*args, **kwargs)

        for line in proc.stdout:
            print(line.decode(), end="")

    except KeyboardInterrupt:
        click.secho("\nCtrl+C pressed, terminating subprocess...", fg="orange")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            click.secho("Subprocess did not terminate in time, killing it...", fg="red")
            proc.kill()
        sys.exit(1)


# actual backporting commands
@cli.command()
@click.argument(
    "commit-id",
    type=str,
    # help="ID of the commit to backport from the upstream repo."
)
@click.argument(
    "branch-name",
    type=str,
    # help="Git ref of the downstream branch we want to backport to (e.g. rhel-9)",
)
@click.pass_context
def create(ctx, commit_id: str, branch_name: str):
    """
    The create command makes the following assumptions:
    """
    # configure variables
    upstream_dirname = "upstream"
    downstream_dirname = "downstream-distgit"
    configfile = ctx.obj["config"]
    if not exists(configfile):
        click.secho(
            f"Config file {configfile} does not exist. Please create one first.",
            fg="red",
        )
        return

    # load config
    conf = config_module.read_config(configfile)

    # temp_dir = "./temp"
    with tempfile.TemporaryDirectory() as _:
        temp_dir = '/home/osilkin/Programming/fixmorph-cli/debug'
        # get the working directory
        pwd_proc = subprocess.run(["pwd"], capture_output=True, cwd="/home/osilkin")
        click.secho(pwd_proc.stdout.decode("utf-8"))
        # with open(os.path.join(temp_dir, "test-file"), "w", encoding="utf-8") as f:
        upstream_path = os.path.join(temp_dir, upstream_dirname)
        downstream_path = os.path.join(temp_dir, downstream_dirname)
        # clone the two repos
        click.secho(f"Cloning upstream repo '{conf.upstream_url}'")
        upstream_clone_proc = subprocess.run(
            ["git", "clone", conf.upstream_url, upstream_path],
            capture_output=True,
            check=True,
            cwd=temp_dir,
        )
        upstream_clone_proc.check_returncode()

        # get the patch we want to backport from the upstream
        checkout_proc = subprocess.run(
            ["git", "-C", upstream_path, "checkout", commit_id],
            check=True,
        )
        upstream_diff_proc = subprocess.run(
            ["git", "-C", upstream_path, "diff", "HEAD~1"],
            capture_output=True,
            check=True,
            cwd=temp_dir,
        )

        if upstream_diff_proc.returncode != 0:
            raise Exception("Error getting the diff from the upstream repo")
        upstream_patch = upstream_diff_proc.stdout.decode("utf-8")
        if not upstream_patch:
            raise Exception("No patch found in the upstream repo")
        upstream_patch_location = os.path.join(temp_dir, "upstream.patch")
        with open(upstream_patch_location, "w", encoding="utf-8") as f:
            f.write(upstream_patch)

        # reset upstream repo to 1 commit before
        subprocess.run(
            ["git", "-C", upstream_path, "reset", "--hard", "HEAD~1"],
            check=True,
            capture_output=True,
            cwd=temp_dir,
        )

        # # write the patch out
        # upstream_patch_file = "upstream-patch.patch"
        # with open(os.path.join(temp_dir, upstream_patch_file), "w", encoding="utf-8") as f:
        #     f.write(upstream_patch)

        click.secho(f"Cloning dist-git repo '{conf.distgit_repo}'")
        downstream_clone_proc = subprocess.run(
            [
                "rhpkg",
                "clone",
                "--anonymous",
                conf.distgit_repo,
                downstream_path,
            ],
            capture_output=True,
            cwd=temp_dir,
        )
        # ensure the clone was successful
        if downstream_clone_proc.returncode != 0:
            click.secho(
                f"Error cloning dist-git repo '{conf.distgit_repo}': {downstream_clone_proc.stderr}",
                fg="red",
            )
            raise RuntimeError(
                f"Error cloning dist-git repo '{conf.distgit_repo}': {downstream_clone_proc.stderr}"
            )

        # switch to desired branch-name
        switch_proc = subprocess.run(
            ["git", "-C", downstream_path, "switch", branch_name],
            check=True,
            capture_output=True,
            cwd=temp_dir,
        )
        if switch_proc.returncode != 0:
            # error
            click.secho(
                f"failed to switch to branch '{branch_name}': {switch_proc.stderr}",
                color="red",
            )
            raise ValueError(f"could not switch to branch {branch_name}")

        sources_proc = subprocess.run(
            ["rhpkg", "sources"], cwd=downstream_path, check=True, capture_output=True
        )
        if sources_proc.returncode != 0:
            click.secho(
                f"failed extracting sources from '{downstream_path}': {sources_proc.stderr}",
                color="red",
            )
            raise RuntimeError(f"could not extract sources from {conf.distgit_repo}")

        # find the sources tarball
        source_tarball = None
        for filename in os.listdir(downstream_path):
            if filename.endswith(".tar.gz"):
                source_tarball = filename
                break

        if not source_tarball:
            click.secho(
                f"could not find source tarball in '{downstream_path}'", color="red"
            )
            raise RuntimeError(
                f"failed to locate source tarball in '{downstream_path}'"
            )

        # extract tarball
        tarball_path = os.path.join(downstream_path, source_tarball)
        extract_tarball_proc = subprocess.run(
            ["tar", "-xf", tarball_path],
            check=True,
            capture_output=True,
            cwd=downstream_path,
        )
        if extract_tarball_proc.returncode != 0:
            click.secho(f"could not extract tarball {tarball_path}", color="red")
            raise RuntimeError(
                f"failed to extract tarball {tarball_path}: {extract_tarball_proc.stderr}"
            )

        downstream_source_dir = tarball_path.strip(".tar.gz")

        # create a symlink to the downstream source directory
        # ln_proc = subprocess.run(
        #     ["ln", "-s", downstream_source_dir, "downstream"],
        #     cwd=temp_dir,
        #     capture_output=True,
        # )
        # if ln_proc.returncode != 0:
        #     click.secho(f"Error creating symlink to downstream source", fg="red")
        #     click.secho(ln_proc.stderr.decode("utf-8"), fg="red")
        #     return
        new_downstream_src_dir = shutil.move(
            downstream_source_dir, os.path.join(temp_dir, "downstream")
        )

        """
        Here's what needs to happen to get the actual downstream source:
        - clone the distgit repo
        - check out one of the rhel branches
        - rhpkg sources to actaully get the archive
        - extract the archive
        - deduce which folder actually contains the source code based on the archive
        """

        # place the dockerfile in the repo
        current_dir = os.path.dirname(os.path.realpath(__file__))
        dockerfile_path = os.path.join(current_dir, "dockerfiles", "Dockerfile.frr")
        shutil.copy(dockerfile_path, os.path.join(temp_dir, "Dockerfile"))

        dockerfile_contents = read_dockerfile()
        click.secho(dockerfile_contents, fg="green")

        # place the run-demo.sh script in the repo
        current_dir = os.path.dirname(os.path.realpath(__file__))
        script_path = os.path.join(current_dir, "scripts", "run-demo.sh")
        shutil.copy(script_path, os.path.join(temp_dir, "run-demo.sh"))

        # list out local directory
        ls_proc = subprocess.run(["ls", "-la"], cwd=temp_dir, capture_output=True)
        print(ls_proc.stdout.decode("utf-8"))

        click.secho("contents of the downstream directory:", fg="green")
        for item in os.listdir(downstream_path):
            print(item)

        command = [
            "docker",
            "build",
            temp_dir,
            "--platform",
            "linux/amd64",
            "-t",
            f"fixmorph-frr:{commit_id}",
            "--build-arg",
            f"PKG_NAME=frr",
            "--build-arg",
            f"--CONFIG_COMMAND_A={FRR_CONFIGURE}",
            "--build-arg",
            f"--CONFIG_COMMAND_B={FRR_CONFIGURE}",
            "--build-arg",
            f"--CONFIG_COMMAND_C={FRR_CONFIGURE}",
            "--build-arg",
            f"BUILD_COMMAND_A={FRR_BUILD}",
            "--build-arg",
            f"BUILD_COMMAND_B={FRR_BUILD}",
            "--build-arg",
            f"BUILD_COMMAND_C={FRR_BUILD}",
            "--build-arg",
            "GIT_EMAIL=user@example.com",
            "--build-arg",
            f"GIT_NAME=user",
        ]
        print(f"command being ran: '{command}'")
        print(f"temp_dir: {temp_dir}")

        # build & run the image
        try:
            # list out contents at repo
            proc = subprocess.Popen(
                command,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
            )

            while True:
                output = proc.stdout.readline()
                if output == "" and proc.poll() is not None:
                    break
                if output:
                    print(output.strip())

            rc = proc.poll()

            if rc != 0:
                if proc.stderr:
                    print(f"Error building the Docker image:\n{proc.stderr.read()}")
                if proc.stdout:
                    print(f"Error building the Docker image:\n{proc.stdout.read()}")
                return
            else:
                print("Docker image built successfully 🥳")
        except KeyboardInterrupt:
            print("\nCtrl+C pressed, terminating subprocess...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Subprocess did not terminate in time, killing it.")
                proc.kill()
            sys.exit(1)

        # if res.returncode != 0:
        #     click.secho(f"Error building the docker image:", fg="red")
        #     click.secho(res.stderr.decode("utf-8"), fg="red")
        #     return

        # run the image
        try:
            # list out contents at repo
            proc = subprocess.Popen(
                ["docker", "run", f"fixmorph-frr:{commit_id}"],
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
            )

            while True:
                output = proc.stdout.readline()
                if output == "" and proc.poll() is not None:
                    break
                if output:
                    print(output.strip())

            rc = proc.poll()

            if rc != 0:
                print(f"Error building the Docker image:\n{proc.stderr.read()}")
                return
            else:
                print("Docker image built successfully 🥳")
        except KeyboardInterrupt:
            print("\nCtrl+C pressed, terminating subprocess...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Subprocess did not terminate in time, killing it.")
                proc.kill()
            sys.exit(1)

        # extract the file from the finished container. It will be located in /fixmorph/output/generated-patch
        subprocess.run(
            [
                "docker",
                "cp",
                f"fixmorph-frr:{commit_id}:/fixmorph/output/generated-patch",
                os.path.join(temp_dir, "generated-patch"),
            ],
            capture_output=True,
            check=True,
        )
        # print out the generated patch
        with open(os.path.join(temp_dir, "generated-patch", "patch.diff"), "r") as f:
            print(f.read())


@config.command()
@click.argument("field")
@click.argument("value")
@click.pass_context
def set(ctx, field: str, value: str):
    configfile = ctx.obj["config"]
    if not exists(configfile):
        click.secho(
            f"Config file {configfile} does not exist. Please create one first.",
            fg="red",
        )
        return

    # load config
    conf = config_module.read_config(configfile)

    if field not in conf.__dict__:
        click.secho(f"Invalid field name: {field}", fg="red")
        return

    # set the new value
    setattr(conf, field, value)

    # save the updated config
    conf.to_file(configfile)
    click.secho(f"Updated {field} in config file to {value}", fg="green")
