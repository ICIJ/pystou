from typing import Annotated, Optional

import typer

# Shared Annotated Typer option types for reusable command definitions
DirectoryArg = Annotated[str, typer.Argument(help="Directory to start from (default: current).")]
RecursiveOpt = Annotated[
    bool, typer.Option("-r", "--recursive", help="Recurse into subdirectories.")
]
DryRunOpt = Annotated[bool, typer.Option("-n", "--dry-run", help="Do not make any changes.")]
LogDirOpt = Annotated[
    Optional[str],
    typer.Option("--log-dir", help="Directory for log files [default: XDG state dir]."),
]
ManifestDirOpt = Annotated[
    Optional[str],
    typer.Option("--manifest-dir", help="Directory for rename manifests [default: XDG state dir]."),
]
DbDirOpt = Annotated[
    Optional[str],
    typer.Option("--db-dir", help="Directory for index databases [default: XDG cache dir]."),
]
TrashDirOpt = Annotated[
    Optional[str],
    typer.Option("--trash-dir", help="Override the trash location (same filesystem)."),
]
HardDeleteOpt = Annotated[
    bool, typer.Option("--hard-delete", help="Permanently delete instead of quarantining.")
]
