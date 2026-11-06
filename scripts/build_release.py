"""Build a source-only ZIP, never recursively archive a work directory."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

from check_release import ROOT, source_files, check_index

sys.path.insert(0, str(ROOT))
from config import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    files = source_files()
    if (ROOT / '.git').exists():
        check_index()
    output = args.output_dir.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Place release archives outside the source repository')
    output.mkdir(parents=True, exist_ok=True)
    name = 'filegdb-inspector-' + VERSION
    archive = output / (name + '.zip')
    checksum = output / (name + '.zip.sha256')
    if archive.exists() or checksum.exists():
        raise FileExistsError('Release output already exists')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for relative, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name + '/' + relative, (2026, 11, 6, 0, 0, 0))
            info.create_system = 3
            mode = 0o100755 if relative in {'start.sh', 'start.command', '.githooks/pre-commit'} else 0o100644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
        for relative, raw in files.items():
            assert z.read(name + '/' + relative) == raw
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with checksum.open('x', encoding='utf-8') as f:
        f.write(digest + '  ' + archive.name + '\n')
    print('Created %s (%d source files, %d bytes)' % (archive.name, len(files), archive.stat().st_size))
    print('SHA256 ' + digest)


if __name__ == '__main__':
    main()
