import { resolveAsset } from './newsData';

export function imageSrcset(variants = []) {
  const seen = new Set();
  return (Array.isArray(variants) ? variants : []).filter(item => {
    if (!item?.url || !Number.isFinite(Number(item.width)) || Number(item.width) <= 0 || seen.has(Number(item.width))) return false;
    seen.add(Number(item.width));
    return true;
  }).map(item => `${resolveAsset(item.url)} ${item.width}w`).join(', ');
}

export function originalImageFallback(event) {
  const image = event.currentTarget;
  const original = image.dataset.originalSrc;
  if (!original || image.dataset.usedOriginal === 'true') { image.hidden = true; return; }
  image.dataset.usedOriginal = 'true';
  image.removeAttribute('srcset');
  image.src = resolveAsset(original);
}
