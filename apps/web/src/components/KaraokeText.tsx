import type { JSX } from "react";

export interface KaraokeTextProps {
  /** The page's words, in reading order. */
  words: string[];
  /** Index into `words` of the word currently being spoken, or null if none. */
  activeIndex: number | null;
  /** Called with a word's index when it is clicked. */
  onWordClick: (i: number) => void;
}

/**
 * Renders a page's words as clickable spans, highlighting the one being spoken.
 *
 * @example
 * <KaraokeText words={["Hello", "world"]} activeIndex={0} onWordClick={(i) => seek(i)} />
 */
export function KaraokeText({ words, activeIndex, onWordClick }: KaraokeTextProps): JSX.Element {
  return (
    <p className="karaoke-text">
      {words.map((word, i) => (
        <span
          key={i}
          className="karaoke-word"
          data-word-index={i}
          data-active={i === activeIndex}
          onClick={() => onWordClick(i)}
        >
          {word}{" "}
        </span>
      ))}
    </p>
  );
}
