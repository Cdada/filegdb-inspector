"""Validate an explicit source allowlist, and optionally the Git index."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {'.py', '.md', '.txt', '.js', '.css', '.html', '.sh', '.command', '.yml'}
SPECIAL_NAMES = {'.gitignore', 'LICENSE', '.githooks/pre-commit'}


def validate_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or path.as_posix() != name:
        raise ValueError('Unsafe release path: ' + name)
    if any(part.lower().endswith('.gdb') for part in path.parts):
        raise ValueError('Data directory forbidden: ' + name)
    if name not in SPECIAL_NAMES and path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError('Non-source file forbidden: ' + name)
    if any(part.lower() in {'runtime', 'data', 'exports', 'logs', '.git', '__pycache__'} for part in path.parts):
        raise ValueError('Runtime/private path forbidden: ' + name)


def validate_content(name, raw):
    if len(raw) > 1_000_000 or b'\x00' in raw:
        raise ValueError('Unexpected binary or oversized file: ' + name)
    content = raw.decode('utf-8')
    # Construct prefixes so the scanner does not flag its own patterns.
    local_prefixes = ['/' + 'Users/', '/' + 'Volumes/', 'C:' + '\\Users\\']
    if any(prefix in content for prefix in local_prefixes):
        raise ValueError('Personal absolute path found: ' + name)
    if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', content):
        raise ValueError('Private key found: ' + name)
    if re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}', content):
        raise ValueError('Possible credential found: ' + name)
    return raw


def load_allowlist(root=ROOT):
    manifest = root / 'RELEASE_FILES.txt'
    if manifest.is_symlink():
        raise ValueError('Release allowlist cannot be a symlink')
    names = [s.strip() for s in manifest.read_text(encoding='utf-8').splitlines() if s.strip()]
    if len(set(names)) != len(names) or 'RELEASE_FILES.txt' not in names:
        raise ValueError('Invalid release allowlist')
    for name in names:
        validate_name(name)
    return names


def source_files(root=ROOT):
    result = {}
    for name in load_allowlist(root):
        path = root / name
        if any((root / Path(*PurePosixPath(name).parts[:i])).is_symlink()
               for i in range(1, len(PurePosixPath(name).parts) + 1)):
            raise ValueError('Symlink forbidden: ' + name)
        if not path.is_file():
            raise ValueError('Missing release file: ' + name)
        result[name] = validate_content(name, path.read_bytes())
    return result


def check_index(root=ROOT):
    top = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=root, text=True).strip()
    if Path(top).resolve() != root.resolve():
        raise ValueError('Run only inside the independent repository root')
    # The staged manifest, not the worktree copy, controls a commit.
    manifest = subprocess.check_output(['git', 'show', ':RELEASE_FILES.txt'], cwd=root).decode('utf-8')
    allowed = {line.strip() for line in manifest.splitlines() if line.strip()}
    for name in allowed:
        validate_name(name)
    entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root)
    tracked = set()
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        info, raw_name = entry.split(b'\t', 1)
        mode, oid, stage = info.decode().split()
        name = raw_name.decode('utf-8')
        if name not in allowed or mode not in ('100644', '100755') or stage != '0':
            raise ValueError('Unapproved or nonregular tracked file: ' + name)
        validate_name(name)
        raw = subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=root)
        validate_content(name, raw)
        tracked.add(name)
    if tracked != allowed:
        raise ValueError('Staged file set does not match release allowlist')
    return len(tracked)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    files = source_files()
    if args.staged:
        check_index()
    print('PASS: %d source files; no data, GDB, JSON, personal paths or detected credentials in release inputs.' % len(files))


if __name__ == '__main__':
    main()
