/**
 * Maps a moment in playback to the word being spoken then.
 *
 * @example
 * const spans = [{ wordIndex: 0, start: 0, end: 1 }, { wordIndex: 1, start: 1, end: 2 }];
 * activeIndex(spans, 1.5); // 1
 */

/** The stretch of playback time during which one word is spoken. */
export interface Span {
  wordIndex: number;
  start: number;
  end: number;
}

/**
 * Index into spans of the word active at instant t, clamped to the timeline.
 * Spans must be contiguous and ascending. Binary search, O(log n).
 *
 * @example activeIndex([{wordIndex:0,start:0,end:1},{wordIndex:1,start:1,end:2}], 1.5) // 1
 */
export function activeIndex(spans: Span[], t: number): number | null {
  if (spans.length === 0) return null;
  if (t <= spans[0].start) return 0;
  if (t >= spans[spans.length - 1].end) return spans.length - 1;
  let lo = 0;
  let hi = spans.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (spans[mid].start <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}
