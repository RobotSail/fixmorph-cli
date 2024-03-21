import os
import shutil
import subprocess
from . import backport
from . import config as config_module
import click
import logging
import sys
import yaml
from os.path import exists, abspath
import tempfile


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


# actual backporting commands
@cli.command()
@click.pass_context
def create(ctx):
    """
    The create command makes the following assumptions:
    """
    configfile = ctx.obj["config"]
    if not exists(configfile):
        click.secho(
            f"Config file {configfile} does not exist. Please create one first.",
            fg="red",
        )
        return

    # load config
    conf = config_module.read_config(configfile)

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Created temporary directory: {temp_dir}")

        # clone the two repos
        upstream_clone_proc = subprocess.run(
            ["git", "clone", conf.upstream_url, os.path.join(temp_dir, "/upstream")],
            capture_output=True,
            check=True,
        )
        print(upstream_clone_proc.stdout.decode())
        print(upstream_clone_proc.stderr.decode())
        results = subprocess.run(
            ["ls", "-al", temp_dir + "/upstream"], check=True, capture_output=True
        )
        print(results.stdout.decode())

        downstream_clone_proc = subprocess.run(
            [
                "rhpkg",
                "clone",
                "--anonymous",
                conf.distgit_repo,
                os.path.join(temp_dir, "/distgit"),
            ],
            capture_output=True,
        )
        print(downstream_clone_proc.stdout.decode())
        print(downstream_clone_proc.stderr.decode())
        listoutput = subprocess.run(
            ["ls", "-al", os.path.join(temp_dir, "/distgit")], capture_output=True
        )
        print(listoutput.stdout.decode())


@config.command()
@click.argument("field")
@click.argument("value")
@click.pass_context
def set(ctx, field, value):
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
