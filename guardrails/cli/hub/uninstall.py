import os
import subprocess
import sys
from typing import List, Literal

import typer

from guardrails.cli.hub.hub import hub_command
from guardrails.cli.logger import LEVELS, logger
from guardrails.cli.server.hub_client import get_validator_manifest
from guardrails.cli.server.module_manifest import ModuleManifest

from utils import (
    get_site_packages_location, 
    get_org_and_package_dirs, 
    get_hub_directory
)
from .console import console

json_format: Literal["json"] = "json"
string_format: Literal["string"] = "string"

def update_file(file_path: str, line_content: str, remove: bool = False):
    with open(file_path, "r+") as file:
        lines = file.readlines()
        file.seek(0)
        if remove:
            lines = [line for line in lines if line.strip() != line_content.strip()]
        file.writelines(lines)
        file.truncate()

def remove_from_hub_inits(manifest: ModuleManifest, site_packages: str):
    org_package = get_org_and_package_dirs(manifest)
    exports: List[str] = manifest.exports or []
    sorted_exports = sorted(exports, reverse=True)
    module_name = manifest.module_name
    relative_path = ".".join([*org_package, module_name])
    import_line = (
        f"from guardrails.hub.{relative_path} import {', '.join(sorted_exports)}"
    )

    # Remove import line from main __init__.py
    hub_init_location = os.path.join(site_packages, "guardrails", "hub", "__init__.py")
    update_file(hub_init_location, import_line, remove=True)

    # Remove import line from namespace __init__.py
    namespace = org_package[0]
    namespace_init_location = os.path.join(
        site_packages, "guardrails", "hub", namespace, "__init__.py"
    )
    update_file(namespace_init_location, import_line, remove=True)

def uninstall_hub_module(manifest: ModuleManifest, site_packages: str):
    uninstall_directory = get_hub_directory(manifest, site_packages)
    logger.info(f"Removing directory {uninstall_directory}")
    subprocess.check_call(["rm", "-rf", uninstall_directory])


@hub_command.command()
def uninstall(
    package_uri: str = typer.Argument(
        help="URI to the package to uninstall. Example: hub://guardrails/regex_match."
    ),
):
    """Uninstall a validator from the Hub."""
    if not package_uri.startswith("hub://"):
        logger.error("Invalid URI!")
        sys.exit(1)

    console.print(f"\nUninstalling {package_uri}...\n")
    logger.log(
        level=LEVELS.get("SPAM"),
        msg=f"Uninstalling {package_uri}...",
    )

    # Validation
    module_name = package_uri.replace("hub://", "")

    # Prep
    with console.status("Fetching manifest", spinner="bouncingBar"):
        module_manifest = get_validator_manifest(module_name)
        site_packages = get_site_packages_location()

    # Uninstall
    with console.status("Removing module", spinner="bouncingBar"):
        uninstall_hub_module(module_manifest, site_packages)

    # Cleanup
    with console.status("Cleaning up", spinner="bouncingBar"):
        remove_from_hub_inits(module_manifest, site_packages)

    console.print("✅ Successfully uninstalled!")  # type: ignore
    logger.log(level=LEVELS.get("SPAM"), msg="✅ Successfully uninstalled!")  # type: ignore
