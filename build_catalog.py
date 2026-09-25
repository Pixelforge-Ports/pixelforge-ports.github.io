"""Build the website from public Pixelforge-Ports repositories and releases."""
from pathlib import Path
import html
import json
import re

from github_catalog import discover
from game_requirements import game_requirements
from release_notes import render_release_history
from support_section import render_support


ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'


def esc(s):
    return html.escape(str(s), quote=True)


def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    return re.sub(
        r'\[([^\]]+)\]\((https://[^ )]+)\)',
        r'<a href="\2">\1</a>',
        s
    )


def prose(s):
    result = []

    for p in s.strip().split('\n\n'):
        if p.startswith('```'):
            result.append(
                '<pre><code>'
                + esc('\n'.join(p.splitlines()[1:-1]))
                + '</code></pre>'
            )
        else:
            result.append(
                '<p>'
                + inline(p.replace('\n', ' '))
                + '</p>'
            )

    return ''.join(result)


def section(s, name):
    match = re.search(
        r'^## ' + re.escape(name) + r'\s*\n(.*?)(?=^## |\Z)',
        s,
        re.M | re.S
    )

    return match.group(1).strip() if match else ''


def header(prefix='./'):
    return f'''<a class="skip" href="#main">Skip to content</a><header class="masthead"><div class="nav-wrap"><a class="brand" href="{prefix}index.html" aria-label="PixelForge Ports home"><span class="brand-mark" aria-hidden="true">PF</span><span>PIXELFORGE<span class="brand-sub">PORTS <b>/</b> BY RONAX</span></span></a><nav aria-label="Main navigation"><a href="{prefix}index.html#ports">THE PORTS</a><a href="{prefix}index.html#install">HOW TO PLAY</a><a href="{prefix}index.html#about">THE FORGE</a><a class="github-link" href="https://github.com/Pixelforge-Ports">GITHUB ↗</a></nav></div></header>'''


def footer(prefix='./'):
    return (
        render_support(
            json.loads(
                (ROOT / 'support-links.json').read_text(encoding='utf-8')
            ),
            prefix
        )
        +
        f'''<footer><a class="footer-brand" href="{prefix}index.html">PIXELFORGE <span>PORTS</span></a><p>Independent ports. Small screens. Big adventures.</p><div class="footer-bottom"><span>© 2026 Pixelforge Ports contributors</span><span>Game names and artwork belong to their respective creators.</span><a href="{prefix}credits.html">Credits & licenses</a></div></footer>'''
    )


def head(
    title,
    prefix='./',
    desc='Indie adventures, forged for your retro handheld. Browse ARM Linux ports by Pixelforge ports (Ronax).'
):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0c101b"><meta name="description" content="{esc(desc)}"><title>{esc(title)} · PixelForge Ports</title><link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{prefix}styles.css"></head><body>'''


def write(name, text):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        text,
        encoding='utf-8',
        newline='\n'
    )


def normalize_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):
        return [value]

    return []


def runtime_label(runtime):
    runtime_text = str(runtime)
    runtime_lower = runtime_text.lower()

    if 'weston' in runtime_lower:
        return 'Westonpack'

    if (
        'zulu17' in runtime_lower
        or 'java17' in runtime_lower
        or 'java_17' in runtime_lower
    ):
        return 'Java 17'

    if (
        'zulu21' in runtime_lower
        or 'java21' in runtime_lower
        or 'java_21' in runtime_lower
    ):
        return 'Java 21'

    if (
        'zulu11' in runtime_lower
        or 'java11' in runtime_lower
        or 'java_11' in runtime_lower
    ):
        return 'Java 11'

    return runtime_text.removesuffix('.squashfs')


records = discover()
catalog = []

for record in records:
    meta = record['meta']
    game = record['id']
    title = meta['title']
    readme = record['readme']

    for folder in ['assets/games', 'guides']:
        (OUT / folder).mkdir(
            parents=True,
            exist_ok=True
        )

    (OUT / 'assets/games' / (game + '.png')).write_bytes(
        record['screenshot']
    )

    digest = record['sha256']

    data = {
        k: record[k]
        for k in [
            'id',
            'zip',
            'size',
            'sha256',
            'repository',
            'ref',
            'download_url',
            'release_url',
            'version',
            'prerelease',
            'releases'
        ]
    }

    requirements = game_requirements(readme)

    requirement_instructions = (
        requirements.get('instructions')
        or ''
    )

    # Android detection.
    #
    # Some Android ports do not have the "## Get ..." section expected by
    # game_requirements.py. NFS Most Wanted, for example, puts its APK/OBB
    # instructions under "## Installation".
    #
    # Inspect the complete README and port metadata as a fallback.
    android_source = '\n'.join([
        readme,
        str(meta.get('desc') or ''),
        str(meta.get('inst') or ''),
        requirement_instructions,
    ])

    android_hint = bool(
        re.search(
            r'\bAndroid\b|\bAPK\b|\.apk\b|\bOBB\b|\.obb\b',
            android_source,
            re.I
        )
    )

    is_android = (
        requirements.get('platform') == 'Android'
        or android_hint
    )

    game_platform = (
        'Android'
        if is_android
        else requirements.get('platform', 'Windows')
    )

    data.update(
        title=title,
        description=meta['desc'],
        genres=meta['genres'],
        windows_version=(
            None
            if is_android
            else requirements.get('windows_version')
        ),
        game_version=requirements.get('game_version'),
        game_platform=game_platform
    )

    catalog.append(data)

    size = (
        f"{record['size'] / 1024:.0f} KB"
        if record['size'] < 1048576
        else f"{record['size'] / 1048576:.1f} MB"
    )

    archive_name = record['zip']

    status = (
        (
            'Testing release '
            if record['prerelease']
            else 'Release '
        )
        + str(record['version'])
        if record['version']
        else 'No published download yet'
    )

    download = (
        f'<a class="button primary" href="{esc(record["download_url"])}">'
        f'↓ Download from GitHub <small>{size}</small></a>'
        if record['download_url']
        else
        '<p class="notice">No published port ZIP yet. '
        'Check the repository for progress.</p>'
    )

    download += (
        f'<p class="small">{esc(status)}</p>'
        f'<a class="text-link" href="{esc(record["repository"])}">'
        'Source &amp; updates on GitHub ↗</a>'
    )

    checksum = (
        f'<details><summary>Package checksum (GitHub)</summary>'
        f'<code class="checksum">{digest}</code></details>'
        if digest
        else ''
    )

    controls = section(
        readme,
        'Controls'
    )

    rows = [
        line
        for line in controls.splitlines()
        if line.startswith('|')
    ]

    table = (
        '<div class="table-scroll"><table>'
        '<thead><tr><th>Control</th><th>Action</th></tr></thead>'
        '<tbody>'
        +
        ''.join(
            '<tr>'
            +
            ''.join(
                '<td>' + inline(c.strip()) + '</td>'
                for c in row.strip('|').split('|')
            )
            +
            '</tr>'
            for row in rows[2:]
        )
        +
        '</tbody></table></div>'
    )

    controls_note = '\n'.join(
        line
        for line in controls.splitlines()
        if not line.startswith('|')
    )

    special = ''

    if game == 'residual':
        special = (
            '<aside class="notice">'
            '<strong>Community testing: ROCKNIX</strong>'
            '<p>RGDS: gameplay and controls reported working with LibMali. '
            'In Panfrost mode, gameplay works but normal controls were not '
            'received. H700 with Panfrost was reported working. Device and '
            'firmware differences still need investigation.</p>'
            '</aside>'
        )

    game_data = (
        requirement_instructions
        or meta.get(
            'inst',
            'See the repository README for required game files.'
        )
    )

    # Only Windows ports display the Windows/GOG requirement panel.
    requirement_panel = ''

    if game_platform == 'Windows':
        required_version = (
            'Windows ' + requirements['game_version']
            if requirements.get('game_version')
            else 'Exact Windows version not documented'
        )

        installer_note = (
            'Use the full Windows offline backup installer from GOG, '
            'including all accompanying .bin parts. Match the game-file '
            'SHA-256 in the instructions below.'
        )

        requirement_panel = (
            '<aside class="notice">'
            '<strong>Required game version: '
            + esc(required_version)
            + '</strong><p>'
            + installer_note
            + ' The port release number is separate from the original '
            'game version.</p></aside>'
        )

    # Safely handle missing, empty or malformed store metadata.
    store_entries = normalize_list(
        meta.get('store')
    )

    store_links = []

    for store_entry in store_entries:
        if not isinstance(store_entry, dict):
            continue

        game_url = store_entry.get('gameurl')
        store_name = store_entry.get('name')

        if game_url and store_name:
            store_links.append(
                f'<a class="text-link" href="{esc(game_url)}">'
                f'Get the game on {esc(store_name)} ↗</a>'
            )

    store = ''.join(store_links)

    # Developer URL is optional.
    developer_link = ''

    for store_entry in store_entries:
        if not isinstance(store_entry, dict):
            continue

        developer_url = store_entry.get(
            'developerurl'
        )

        if developer_url:
            developer_link = (
                f'<a href="{esc(developer_url)}">'
                'Visit the game developer ↗</a>'
            )
            break

    # ------------------------------------------------------------
    # Dynamic "Before you play" information from port.json
    # ------------------------------------------------------------

    arch_entries = normalize_list(
        meta.get('arch')
    )

    arch_names = {
        'aarch64': '64-bit ARM Linux',
        'arm64': '64-bit ARM Linux',
        'armhf': '32-bit ARM Linux',
        'armv7': '32-bit ARM Linux',
        'armv7l': '32-bit ARM Linux',
        'x86_64': '64-bit x86 Linux',
    }

    platform_names = []

    for arch in arch_entries:
        arch_key = str(arch).lower()

        platform_name = arch_names.get(
            arch_key,
            str(arch)
        )

        if platform_name not in platform_names:
            platform_names.append(
                platform_name
            )

    platform_text = (
        ' / '.join(platform_names)
        or 'Linux'
    )

    # Runtime is taken directly from package/port.json.
    #
    # Example:
    #
    # "runtime": []
    #
    # -> no Runtime row at all.
    #
    # "runtime": [
    #   "weston_pkg_0.2.squashfs",
    #   "zulu17.54.21-ca-jre17.0.13-linux.squashfs"
    # ]
    #
    # -> Runtime: Westonpack + Java 17
    runtime_entries = normalize_list(
        meta.get('runtime')
    )

    runtime_names = []

    for runtime in runtime_entries:
        name = runtime_label(runtime)

        if name and name not in runtime_names:
            runtime_names.append(name)

    specs_runtime = ''

    if runtime_names:
        specs_runtime = (
            '<dt>Runtime</dt>'
            '<dd>'
            + esc(' + '.join(runtime_names))
            + '</dd>'
        )

    # Minimum glibc is also read from each port's metadata.
    min_glibc = meta.get('min_glibc')

    specs_glibc = ''

    if min_glibc:
        specs_glibc = (
            '<dt>Minimum glibc</dt>'
            '<dd>'
            + esc(min_glibc)
            + '</dd>'
        )

    # Use actual porter information from port.json.
    porter_entries = normalize_list(
        meta.get('porter')
    )

    porter_entries = [
        str(porter)
        for porter in porter_entries
        if str(porter).strip()
    ]

    porter_text = (
        ', '.join(porter_entries)
        or 'Pixelforge ports (Ronax)'
    )

    # Only include the runtime installation instruction when runtimes
    # are actually declared by the port.
    runtime_install_step = ''

    if runtime_names:
        runtime_install_step = (
            '<li>Allow PortMaster to download '
            + esc(' and '.join(runtime_names))
            + '. An internet connection is needed if these runtimes '
            'are not installed.</li>'
        )

    release_notes = render_release_history(record.get('releases', []))

    page = (
        head(
            title,
            '../',
            meta['desc']
        )
        +
        header('../')
        +
        f'''<main id="main" class="detail"><a class="back-link" href="../index.html#ports">← Back to the port library</a><div class="detail-hero"><img class="detail-image" src="../assets/games/{game}.png" alt="{esc(title)} gameplay" width="640" height="480"><div><span class="eyebrow">{' / '.join(meta['genres']).upper()}</span><h1>{esc(title)}</h1><p class="lead">{esc(meta['desc'])}</p><div class="tags"><span>ARM LINUX</span><span>GAME FILES REQUIRED</span></div>{requirement_panel}{download}<p class="small">Port files only. Purchase the original game separately.</p>{store}</div></div>{special}<section class="release-notes"><h2>Build release notes</h2><p class="small">Notes are shown for each published release, alongside the build tag they describe.</p>{release_notes}</section><div class="detail-columns"><article><section><h2>Bring your game</h2>{prose(game_data)}</section><section><h2>Install the port</h2><ol class="install-list"><li>Update PortMaster. Copy <strong>{esc(archive_name)}</strong> into its <code>autoinstall/</code> folder and open PortMaster.</li>{runtime_install_step}<li>Copy the owned game files into <code>{game}/</code> as described above. Launch <strong>{esc(title)}</strong> from your ports menu.</li></ol><details><summary>Manual installation paths</summary>{prose(section(readme, 'Installation'))}</details></section><section><h2>Handheld controls</h2>{table}{prose(controls_note)}</section><section><h2>Saves & troubleshooting</h2>{prose(section(readme, 'Saves and troubleshooting'))}</section></article><aside class="specs"><h2>Before you play</h2><dl><dt>Platform</dt><dd>{esc(platform_text)}</dd>{specs_runtime}<dt>Controls</dt><dd>gptokeyb2</dd>{specs_glibc}<dt>Porter</dt><dd>{esc(porter_text)}</dd></dl><p>Compatibility depends on your firmware, graphics driver and game version. Device testing is ongoing.</p>{checksum}{developer_link}</aside></div></main>'''
        +
        footer('../')
        +
        '</body></html>'
    )

    write(
        'guides/' + game + '.html',
        page
    )


catalog.sort(
    key=lambda g: (
        g['id'] != 'residual',
        g['id'] != 'mewnbase',
        g['title']
    )
)

cards = []

for g in catalog:
    cards.append(
        f'''<article class="game-card" data-title="{esc(g['title'].lower())}" data-genres="{esc(' '.join(g['genres']))}"><a class="game-art" href="guides/{g['id']}.html"><img src="assets/games/{g['id']}.png" alt="{esc(g['title'])} gameplay" width="640" height="480" loading="lazy"><span class="art-link">EXPLORE PORT ↗</span></a><div class="game-body"><p class="genre">{esc(' / '.join(g['genres']).upper())}</p><h3><a href="guides/{g['id']}.html">{esc(g['title'])}</a></h3><p class="game-description">{esc(g['description'])}</p><div class="card-bottom"><span>{"TESTING RELEASE" if g["prerelease"] else "BYO GAME DATA" if g["download_url"] else "AWAITING RELEASE"}</span><a href="guides/{g['id']}.html" aria-label="View {esc(g['title'])} installation and download">View port <b>↗</b></a></div></div></article>'''
    )


genres = sorted(
    {
        genre
        for g in catalog
        for genre in g['genres']
    }
)


index = (
    head(
        'Indie games. Handheld adventures.'
    )
    +
    header()
    +
    '''<main id="main"><section class="hero"><div class="hero-content"><p class="eyebrow"><span class="tiny-diamond">◆</span> INDEPENDENT PORTS FOR ARM LINUX</p><h1>SMALL SCREEN.<br>BIG <span>ADVENTURES.</span></h1><p class="hero-copy">Your favorite indie worlds, reforged for retro handhelds.<br>Made for the PortMaster ecosystem by Ronax.</p><a class="button primary" href="#ports">EXPLORE THE PORTS <span>↓</span></a><a class="hero-secondary" href="#install">New to PortMaster? Start here ↗</a></div><div class="hero-caption">THE PIXELFORGE <span>EST. 2026</span></div></section><div class="compat-strip"><span>BUILT FOR THE POCKET</span><strong>ANBERNIC</strong><strong>R36S</strong><strong>TRIMUI</strong><span>Compatible ARM Linux firmware required</span></div><section id="ports" class="library wrap"><div class="section-heading"><div><p class="eyebrow">PICK YOUR NEXT ADVENTURE</p><h2>Fresh from the forge<span class="orange">.</span></h2></div><span class="count-badge">12 PORTS / ARM LINUX</span></div><div class="catalog-tools"><label class="search-box"><span aria-hidden="true">⌕</span><input id="search" type="search" placeholder="Find your next game…" aria-label="Search ports"></label><label class="genre-select">Genre <select id="genre"><option value="">All genres</option>'''
    +
    ''.join(
        f'<option value="{esc(g)}">{esc(g.title())}</option>'
        for g in genres
    )
    +
    '''</select></label><p id="result-count" role="status" aria-live="polite">Showing 12 ports</p></div><div class="game-grid">'''
    +
    ''.join(cards)
    +
    '''</div><div id="empty" class="empty" hidden><h3>No ports found</h3><p>Try another title or genre.</p><button id="reset" class="button">Clear filters</button></div><p class="catalog-note">Every download is a bring-your-own-data package. Original games are sold separately.</p></section><section id="install" class="installation"><div class="wrap"><p class="eyebrow">FROM DOWNLOAD TO D-PAD</p><h2>Three steps. A new adventure.</h2><div class="steps"><article><span class="step-number">01</span><h3>Choose your port</h3><p>Pick a game above. Check the exact required game version in its guide, then download the port ZIP.</p></article><article><span class="step-number">02</span><h3>Install with PortMaster</h3><p>Put the ZIP in PortMaster’s <code>autoinstall/</code> folder. Open PortMaster and let it install the port and any declared runtimes.</p></article><article><span class="step-number">03</span><h3>Bring your game files</h3><p>Copy the files from your purchased game to the folder in its guide. Launch from your handheld’s ports menu.</p></article></div><a class="text-link" href="https://portmaster.games/installation.html">Get PortMaster ↗</a></div></section><section id="about" class="about wrap"><div><p class="eyebrow">MEET THE MAKER</p><h2>A little forge.<br>A love for handhelds.</h2></div><div><p>PixelForge Ports is Ronax’s collection of indie game adaptations for ARM Linux handhelds. The aim is simple: bring more of the games you own to the devices you love.</p><p>These independent ports use PortMaster’s tools and runtimes. They are not official releases from the original game developers. Credit for each game stays with its creators.</p><a class="text-link" href="https://github.com/Pixelforge-Ports">Follow the work on GitHub ↗</a></div></section></main>'''
    +
    footer()
    +
    '''<script src="catalog.js" defer></script></body></html>'''
)


index = (
    index
    .replace(
        '12 PORTS / ARM LINUX',
        str(len(catalog))
        + ' PORTS / ARM LINUX'
    )
    .replace(
        'Showing 12 ports',
        'Showing '
        + str(len(catalog))
        + ' ports'
    )
)


write(
    'index.html',
    index
)


write(
    'catalog.json',
    json.dumps(
        catalog,
        indent=2
    )
    + '\n'
)


# Remove only generated artifacts superseded by the GitHub catalog.
known = {
    g['id']
    for g in catalog
}


for file in (
    OUT / 'guides'
).glob('*.html'):
    if file.stem not in known:
        file.unlink()


for file in (
    OUT / 'assets/games'
).glob('*.png'):
    if file.stem not in known:
        file.unlink()


for file in (
    OUT / 'downloads'
).glob('*'):
    if (
        file.is_file()
        and (
            file.suffix.lower() == '.zip'
            or file.name == 'SHA256SUMS.txt'
        )
    ):
        file.unlink()


write(
    'credits.html',
    head('Credits & licenses')
    +
    header()
    +
    '''<main id="main" class="wrap credits"><p class="eyebrow">THE PEOPLE BEHIND THE PIXELS</p><h1>Credits & licenses</h1><p>Port adaptations: Pixelforge ports (Ronax). Copyright © 2026 Pixelforge Ports contributors.</p><p>Orangepixel created Ashworld, Gunslugs 2, Gunslugs 3, Heroes of Loot, Heroes of Loot 2, Meganoid, Residual, Sir Questionnaire, Snake Core, Space Grunts and Space Grunts 2. Cairn4 created MewnBase. Game screenshots, names and assets remain the property of their respective creators.</p><p>Each download retains its port, host, gptokeyb2 and applicable third-party license notices. Purchased game data is not included.</p><p>Press Start 2P by CodeMan38 is distributed under the <a href="assets/FONT-LICENSE.txt">SIL Open Font License</a>.</p><a class="button" href="index.html#ports">Back to the ports</a></main>'''
    +
    footer()
    +
    '</body></html>'
)


print(
    f'Catalog ready: {len(catalog)} GitHub ports '
    'with release links and individual guides.'
)
