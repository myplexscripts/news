# London News editorial intelligence update

This update completes the planned story clustering, London relevance scoring, and homepage ranking systems. Everything is deterministic and runs for free inside the existing GitHub Action.

## Story clustering

- Compares stories published within a 36 hour window.
- Uses normalized headline similarity, distinctive token overlap, local entity overlap, and publication timing.
- Uses stricter thresholds for stories from the same publisher to avoid combining unrelated follow-ups.
- Keeps every publisher article as its own record and permalink.
- Marks one best-readable article as the cluster representative.
- Homepage cards collapse multi-publisher coverage into one event card.
- Article pages show links to the other publishers covering the same event.

## London relevance

Each story gets a 0 to 100 `local_score` using London and Middlesex entities such as City of London, London Police, Western, Fanshawe, LHSC, London Transit, neighbourhoods, major streets, Middlesex communities, St. Thomas, and Strathroy.

Publisher identity is only a modest prior. It does not automatically make a generic Ontario story highly local. London, UK and United Kingdom context receives strong negative scoring.

Google News remains discovery-only. Google-discovered articles below 25/100 local relevance are removed after full extraction.

## Homepage ranking

The first three homepage event cards are selected by:

- 35% local relevance
- 25% freshness
- 20% number of independent sources
- 10% extraction quality
- 10% image quality

Only events with meaningful local relevance can enter the top three. The rest of the homepage stays chronological.

A dedicated `/latest/` page is also included. It is completely chronological and the mobile Latest tab now links there instead of jumping to the ranked homepage feed.

## Admin visibility

`/admin/` now shows:

- the three promoted stories
- rank score
- local score
- source count
- the exact ranking reasons
- recent multi-source clusters

## New stored metadata

Each article can contain:

- `local_score`
- `local_reasons`
- `image_score`
- `cluster_id`
- `cluster_size`
- `cluster_source_count`
- `cluster_sources`
- `cluster_member_ids`
- `cluster_representative`
- `cluster_representative_id`
- `cluster_latest_published`
- `rank_score`
- `ranking_reasons`
- `freshness_score`

Top-level `news.json` also receives `top_story_ids`, `editorial_clusters`, cluster counts, and the number of low-relevance Google discoveries removed.

## Install

Replace the matching files in your repository and add the new files. Commit normally. Your existing GitHub Action will generate all ranking and cluster metadata on its next run.

No `data/news.json` is included, so this update does not overwrite your story history.

Optional smoke test:

```bash
python scripts/test_editorial.py
```
