export type TimelineStory = {
  id?: string;
  published?: string;
  cluster_latest_published?: string;
  cluster_id?: string;
  cluster_source_count?: number;
  cluster_sources?: string[];
};

const publishedTime = (story: TimelineStory) => {
  const value = Date.parse(String(story.published || ''));
  return Number.isFinite(value) ? value : 0;
};

/**
 * Keep the chronological homepage compact without discarding source-specific stories.
 *
 * Multi-source clusters contribute one homepage card, using the newest report in
 * that cluster. This applies before the featured carousel is selected, so two
 * publishers covering the same event cannot consume multiple carousel slots.
 * Single-source stories remain independent. All original stories stay in news.json
 * and retain their own permalinks for search and alternate-coverage links.
 */
export function collapseTimelineStories<T extends TimelineStory>(input: T[]): T[] {
  const sorted = [...input].sort((a, b) => publishedTime(b) - publishedTime(a));
  const seenMultiSourceClusters = new Set<string>();

  return sorted.filter((story) => {
    const sourceCount = Number(story.cluster_source_count || story.cluster_sources?.length || 1);
    const clusterId = String(story.cluster_id || '');

    if (sourceCount < 2 || !clusterId) return true;
    if (seenMultiSourceClusters.has(clusterId)) return false;

    seenMultiSourceClusters.add(clusterId);
    return true;
  });
}
