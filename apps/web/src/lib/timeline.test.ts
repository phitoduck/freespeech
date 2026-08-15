import { expect, test } from "vitest";
import * as hegel from "@hegeldev/hegel";
import * as gs from "@hegeldev/hegel/generators";
import { activeIndex, type Span } from "./timeline";

/** Reference oracle: the contract, stated as a linear scan. */
function linearScan(spans: Span[], t: number): number | null {
  if (spans.length === 0) return null;
  const last = spans.length - 1;
  if (t <= spans[0].start) return 0;
  if (t >= spans[last].end) return last;
  for (let i = 0; i < spans.length; i++) {
    if (spans[i].start <= t && t < spans[i].end) return i;
  }
  return last;
}

/** A valid, contiguous, ascending timeline: positive durations laid end to end. */
const timelines = gs
  .arrays(gs.integers({ minValue: 1, maxValue: 1000 }), { minSize: 1, maxSize: 30 })
  .map((durations) => {
    let start = 0;
    return durations.map((d, wordIndex): Span => {
      const span = { wordIndex, start, end: start + d };
      start += d;
      return span;
    });
  });

// Instants include negatives, values past the end, and +/-Infinity. NaN is
// excluded: every ordering comparison against it is false, so it has no
// well-defined position on a timeline.
const instants = gs.oneOf(
  gs.integers({ minValue: -10_000, maxValue: 10_000 }),
  gs.floats({ minValue: -1e6, maxValue: 1e6, allowInfinity: false, allowNan: false }),
  gs.sampledFrom([-Infinity, Infinity]),
);

test("agrees with a linear scan", () =>
  hegel.test((tc) => {
    const spans = tc.draw(timelines);
    const t = tc.draw(instants);
    tc.note(`spans=${JSON.stringify(spans)} t=${t}`);
    expect(activeIndex(spans, t)).toBe(linearScan(spans, t));
  }, { testCases: 200 }));

test("never moves backwards as t advances", () =>
  hegel.test((tc) => {
    const spans = tc.draw(timelines);
    let t1 = tc.draw(instants);
    let t2 = tc.draw(instants);
    if (t1 > t2) [t1, t2] = [t2, t1];
    tc.note(`spans=${JSON.stringify(spans)} t1=${t1} t2=${t2}`);
    expect(activeIndex(spans, t1)!).toBeLessThanOrEqual(activeIndex(spans, t2)!);
  }, { testCases: 200 }));

test("always resolves to a valid index into spans", () =>
  hegel.test((tc) => {
    const spans = tc.draw(timelines);
    const t = tc.draw(instants);
    const i = activeIndex(spans, t);
    tc.note(`spans=${JSON.stringify(spans)} t=${t} i=${i}`);
    expect(i).not.toBeNull();
    expect(i! >= 0 && i! < spans.length).toBe(true);
  }, { testCases: 200 }));

test("empty timeline has no active word", () => {
  expect(activeIndex([], 0)).toBeNull();
  expect(activeIndex([], -1)).toBeNull();
  expect(activeIndex([], Infinity)).toBeNull();
});
