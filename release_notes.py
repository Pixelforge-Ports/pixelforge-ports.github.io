"""Safe, small Markdown renderer for notes returned by the GitHub Releases API."""
import html
import re


def _inline(text):
    escaped = html.escape(str(text), quote=True)
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    return re.sub(
        r'\[([^\]]+)\]\((https://[^ )]+)\)',
        r'<a href="\2" rel="noopener noreferrer">\1</a>',
        escaped
    )


def render_markdown(source):
    """Render common release-note Markdown while escaping all raw HTML."""
    lines = str(source or '').replace('\r\n', '\n').split('\n')
    output = []
    paragraph = []
    list_items = []
    list_tag = None
    code = []
    in_code = False

    def flush_paragraph():
        if paragraph:
            output.append('<p>' + _inline(' '.join(x.strip() for x in paragraph)) + '</p>')
            paragraph.clear()

    def flush_list():
        nonlocal list_tag
        if list_items:
            output.append('<' + list_tag + '>' + ''.join('<li>' + _inline(item) + '</li>' for item in list_items) + '</' + list_tag + '>')
            list_items.clear()
            list_tag = None

    for line in lines:
        if line.startswith('```'):
            flush_paragraph()
            flush_list()
            if in_code:
                output.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>')
                code.clear()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r'^(#{1,3})\s+(.+?)\s*#*$', line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1)) + 2
            output.append(f'<h{level}>' + _inline(heading.group(2)) + f'</h{level}>')
            continue
        bullet = re.match(r'^\s*[-*+]\s+(.+)$', line)
        numbered = re.match(r'^\s*\d+[.)]\s+(.+)$', line)
        if bullet or numbered:
            flush_paragraph()
            tag = 'ul' if bullet else 'ol'
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            list_items.append((bullet or numbered).group(1))
            continue
        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    if in_code:
        output.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>')
    return ''.join(output)


def render_release_history(releases):
    if not releases:
        return '<p class="small">No published build releases yet.</p>'

    entries = []
    for index, release in enumerate(releases):
        version = html.escape(str(release.get('version') or 'Untitled release'), quote=True)
        state = 'Testing release' if release.get('prerelease') else 'Release'
        published = release.get('published_at') or ''
        date = html.escape(str(published)[:10], quote=True)
        summary = f'{state} {version}' + (f' · {date}' if date else '')
        body = render_markdown(release.get('notes'))
        if not body:
            body = '<p class="small">No release notes were published for this build.</p>'
        links = []
        release_url = release.get('release_url')
        if release_url and str(release_url).startswith('https://github.com/'):
            links.append(f'<a href="{html.escape(str(release_url), quote=True)}" rel="noopener noreferrer">View release on GitHub ↗</a>')
        download_url = release.get('download_url')
        if download_url and str(download_url).startswith('https://github.com/'):
            links.append(f'<a href="{html.escape(str(download_url), quote=True)}" rel="noopener noreferrer">Download this build ↗</a>')
        footer = '<p class="release-note-links">' + ' <span aria-hidden="true">·</span> '.join(links) + '</p>' if links else ''
        open_attr = ' open' if index == 0 else ''
        entries.append(f'<details class="release-entry"{open_attr}><summary>{summary}</summary><div class="release-note-body">{body}{footer}</div></details>')
    return '<div class="release-history">' + ''.join(entries) + '</div>'
