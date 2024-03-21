import typing
from dataclasses import dataclass
from pathlib import Path
import click
import yaml


DEFAULT_CONFIG = "config.yaml"
DEFAULT_FIXMORPH_BASE_IMAGE = "quay.io/cve-gen-ai/et-fixmorph:latest"

@dataclass
class BackporterConfig:
    fixmorph_base_image: typing.Optional[str]
    upstream_url: str
    distgit_repo: str

    def to_file(self, fp: str):
        """
        Writes the config to the specified file stream.
        """
        try:
            with open(fp, "w", encoding="utf-8") as fstream:
                yaml.dump(self.__dict__, fstream)
        except Exception as e:
            print(f"An error occurred while writing to the file: {e}")


def read_config(fp: str) -> BackporterConfig:
    """
    Reads a config at the specified path
    and returns a BackporterConfig object.
    """
    with open(fp, "r", encoding="utf-8") as infile:
        raw_config: dict = yaml.load(infile, Loader=yaml.FullLoader)
    
    config = BackporterConfig(
        distgit_repo=raw_config["distgit_repo"],
        fixmorph_base_image=raw_config.get("fixmorph_base_image"),
        upstream_url=raw_config["upstream_url"],
    )
    return config


    