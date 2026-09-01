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
 * Prepare articles for the homepage timeline.
 *
 * The homepage is an article feed, not an event-cluster feed. Every collected
 * article stays independent, even when several publishers cover the same event.
 * Each card also uses its own publication timestamp so a cluster update from a
 * different publisher can never move an older article ahead of a newer one.
 */
export function collapseTimelineStories<T extends TimelineStory>(input: T[]): T[] {
  return [...input]
    .map((story) => ({
      ...story,
      cluster_latest_published: story.published || story.cluster_latest_published
    }))
    .sort((a, b) => publishedTime(b) - publishedTime(a)) as T[];
}
