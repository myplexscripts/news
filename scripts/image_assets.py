"""Recover source-matched local media and generate responsive WebP derivatives."""
from __future__ import annotations
import hashlib
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def variants_for(path, widths, quality=82):
    path = Path(path)
    results = []
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened)
        image = image.convert('RGBA' if image.mode in {'RGBA', 'LA'} or 'transparency' in image.info else 'RGB')
        used = set()
        for requested in widths:
            width = min(requested, image.width)
            if width in used:
                continue
            used.add(width)
            height = max(1, round(image.height * width / image.width))
            output = path.with_name(f'{path.stem}-responsive-{width}-q{quality}.webp')
            if not output.exists():
                resized = image.resize((width, height), Image.Resampling.LANCZOS) if width != image.width else image
                resized.save(output, 'WEBP', quality=quality, method=4)
            results.append({'url': output.relative_to(PUBLIC).as_posix(), 'width': width, 'height': height})
    return results


def local_source(value):
    text = str(value or '')
    if not text or text.startswith(('http:', 'https:')):
        return None
    path = PUBLIC / text.removeprefix('/news/').lstrip('/')
    return path if path.is_file() and path.resolve().is_relative_to(PUBLIC.resolve()) else None


def cached_original(url):
    local = local_source(url)
    if local:
        return local
    digest = hashlib.sha256(str(url).encode('utf-8')).hexdigest()[:24]
    # Prefer the current higher-resolution cache, but keep v1 as a safe fallback
    # while the deferred image pass refreshes this week's archive.
    for version in ('v2', 'v1'):
        candidate = PUBLIC / 'cache/editorial' / f'{version}-{digest}.webp'
        if candidate.is_file():
            return candidate
    return None


def attach_cached_images(stories):
    count = 0
    for story in stories:
        hero = str(story.get('image') or '')
        original = cached_original(hero)
        if original:
            try:
                with Image.open(original) as image:
                    width, height = image.size
                story.update(editorial_image=original.relative_to(PUBLIC).as_posix(), editorial_image_source=hero,
                             editorial_image_width=width, editorial_image_height=height)
                story['editorial_image_variants'] = variants_for(original, [640, 960, 1600, 2400], 86)
                story['card_image_variants'] = variants_for(original, [320, 640, 1200], 80)
                story['card_image_source'] = hero
                story['card_image_small'] = story['card_image_variants'][0]['url']
                story['card_image'] = story['card_image_variants'][-1]['url']
                count += 1
            except (OSError, ValueError):
                pass
        else:
            # Older collectors stored card derivatives without retaining their
            # references. Recover only the exact source URL's matching cache key.
            stem = hashlib.sha1(hero.encode('utf-8')).hexdigest()[:20]
            refs = []
            for suffix in ('-sm', ''):
                path = PUBLIC / 'cache/news' / f'{stem}{suffix}.webp'
                if path.is_file():
                    try:
                        with Image.open(path) as image:
                            refs.append({'url': path.relative_to(PUBLIC).as_posix(), 'width': image.width, 'height': image.height})
                    except OSError: pass
            if refs:
                story['card_image_variants'] = sorted({item['width']:item for item in refs}.values(), key=lambda item:item['width'])
                story['card_image_source'] = hero
                story['card_image_small'] = refs[0]['url']
                story['card_image'] = refs[-1]['url']
        for block in story.get('content_blocks') or []:
            if not isinstance(block, dict) or block.get('type') != 'image':
                continue
            original = cached_original(block.get('url'))
            if not original:
                continue
            try:
                block['optimized_url'] = original.relative_to(PUBLIC).as_posix()
                block['optimized_url_source'] = block['url']
                block['image_variants'] = variants_for(original, [640, 960, 1600, 2400], 86)
                with Image.open(original) as image:
                    block['width'], block['height'] = image.size
            except (OSError, ValueError): pass
    return count
