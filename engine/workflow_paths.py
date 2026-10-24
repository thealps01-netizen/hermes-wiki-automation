"""Shared containment checks for review and constrained drafting."""
from pathlib import Path
import re
import stat


class PathRefused(RuntimeError):
    pass


def _reject_links(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PathRefused('Path metadata is unreadable') from exc
    if (stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        raise PathRefused('Linked path refused')
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
        raise PathRefused('Hard-linked input refused')


def checked_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative or '\0' in relative:
        raise PathRefused('Invalid relative path')
    parts = relative.split('/')
    if any(p in ('', '.', '..') or p.endswith(('.', ' ')) for p in parts):
        raise PathRefused('Path traversal or ambiguous spelling')
    root = Path(root)
    absolute = root.absolute()
    for ancestor in [*reversed(absolute.parents), absolute]:
        _reject_links(ancestor)
    current = root
    for part in [None, *parts]:
        if part is not None:
            if current.is_dir():
                matches = [p.name for p in current.iterdir() if p.name.casefold() == part.casefold()]
                if matches and matches != [part]:
                    raise PathRefused('Path case mismatch or collision')
            current = current / part
        _reject_links(current)
    try:
        current.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise PathRefused('Path escapes root') from exc
    return current


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value):
        raise PathRefused('Invalid identifier')
    if value.endswith(('.', ' ')):
        raise PathRefused('Ambiguous identifier')
    return value
