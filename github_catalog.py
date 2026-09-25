"""Discover public port repositories and published release ZIPs from GitHub."""
import json, os, re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

ORG = 'Pixelforge-Ports'
API = 'https://api.github.com'


def request(url, optional=False):
    headers = {
        'User-Agent': 'Pixelforge-Ports-Catalog',
        'Accept': 'application/vnd.github+json'
    }

    if url.startswith(API + '/') and os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']

    try:
        with urlopen(
            Request(url, headers=headers),
            timeout=40
        ) as response:
            return response.read()

    except HTTPError as error:
        if optional and error.code == 404:
            return None

        raise RuntimeError(
            f'GitHub request failed ({error.code}): {url}. '
            'Existing published site is unchanged.'
        ) from None


def pages(path):
    page = 1

    while True:
        values = json.loads(
            request(
                f'{API}{path}?per_page=100&page={page}'
            )
        )

        if not isinstance(values, list):
            raise ValueError('Expected a GitHub list')

        yield from values

        if len(values) < 100:
            break

        page += 1


def raw(repo, ref, path, optional=False):
    return request(
        f'https://raw.githubusercontent.com/'
        f'{ORG}/{quote(repo, safe="")}/'
        f'{quote(ref, safe="")}/{path}',
        optional
    )


def choose_release(releases, archive_name):
    expected = archive_name.lower()

    for release in sorted(
        (
            r
            for r in releases
            if not r.get('draft')
        ),
        key=lambda r: r.get('published_at') or '',
        reverse=True
    ):
        assets = [
            a
            for a in release.get('assets', [])
            if (
                a['name'].lower() == expected
                and a.get('state') == 'uploaded'
            )
        ]

        if len(assets) == 1:
            return release, assets[0]

    return None, None


def release_history(releases, archive_name):
    """Return every published release with its notes and matching build asset."""
    expected = archive_name.lower()
    history = []

    for release in sorted(
        (r for r in releases if not r.get('draft')),
        key=lambda r: r.get('published_at') or '',
        reverse=True
    ):
        assets = [
            asset
            for asset in release.get('assets', [])
            if asset.get('name', '').lower() == expected
            and asset.get('state') == 'uploaded'
        ]
        asset = assets[0] if len(assets) == 1 else None
        digest = asset.get('digest') if asset else None
        history.append({
            'version': release.get('tag_name') or 'Untitled release',
            'published_at': release.get('published_at'),
            'prerelease': bool(release.get('prerelease')),
            'release_url': release.get('html_url'),
            'notes': release.get('body') or '',
            'download_url': asset.get('browser_download_url') if asset else None,
            'size': asset.get('size') if asset else None,
            'sha256': (
                digest[7:]
                if isinstance(digest, str)
                and re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
                else None
            )
        })

    return history


def discover():
    records = []

    for repo in pages(f'/orgs/{ORG}/repos'):
        if repo.get('archived') or repo.get('private'):
            continue

        name = repo['name']
        ref = repo['default_branch']

        metadata = raw(
            name,
            ref,
            'package/port.json',
            True
        )

        if metadata is None:
            continue

        metadata = json.loads(metadata)

        game = metadata['name'].removesuffix('.zip')

        if not re.fullmatch(r'[a-z0-9_-]+', game):
            raise ValueError('Unsafe port ID')

        releases = list(pages(f'/repos/{ORG}/{name}/releases'))
        history = release_history(releases, metadata['name'])
        release, asset = choose_release(releases, metadata['name'])

        # A release's guide and screenshot must describe that release,
        # not unpublished changes.
        if release:
            ref = release['tag_name']

            release_metadata = raw(
                name,
                ref,
                'package/port.json',
                True
            )

            if release_metadata is None:
                raise ValueError(
                    f'{name}: release {ref} needs '
                    'package/port.json at its tag'
                )

            metadata = json.loads(
                release_metadata
            )

        readme = (
            raw(
                name,
                ref,
                'package/README.md',
                True
            )
            or
            raw(
                name,
                ref,
                'README.md'
            )
        )

        screenshot = raw(
            name,
            ref,
            'package/screenshot.png'
        )

        if not screenshot.startswith(
            b'\x89PNG\r\n\x1a\n'
        ):
            raise ValueError(
                f'{name}: invalid screenshot'
            )

        attrs = metadata['attr']

        if (
            not isinstance(
                attrs.get('title'),
                str
            )
            or
            not isinstance(
                attrs.get('genres'),
                list
            )
        ):
            raise ValueError(
                f'{name}: invalid metadata'
            )

        item = {
            'id': game,
            'meta': attrs,
            'readme': readme.decode('utf-8-sig'),
            'screenshot': screenshot,
            'repository': repo['html_url'],
            'ref': ref,
            'zip': (
                asset['name']
                if asset
                else metadata['name']
            ),
            'download_url': (
                asset['browser_download_url']
                if asset
                else None
            ),
            'size': (
                asset['size']
                if asset
                else 0
            ),
            'sha256': None,
            'release_url': (
                release['html_url']
                if release
                else None
            ),
            'version': (
                release['tag_name']
                if release
                else None
            ),
            'prerelease': (
                release['prerelease']
                if release
                else False
            ),
            'releases': history
        }

        if (
            asset
            and asset.get('digest', '')
            and re.fullmatch(
                r'sha256:[0-9a-f]{64}',
                asset['digest']
            )
        ):
            item['sha256'] = (
                asset['digest'][7:]
            )

        records.append(item)

        print(
            f"FOUND {game}: "
            f"{item['version'] or 'no published ZIP'}",
            flush=True
        )

    if not records:
        raise ValueError(
            'No ports found; refusing to publish '
            'an empty catalog'
        )

    if (
        len({r['id'] for r in records})
        != len(records)
    ):
        raise ValueError(
            'Duplicate port IDs in organization'
        )

    return records
