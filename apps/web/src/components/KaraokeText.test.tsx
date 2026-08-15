import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KaraokeText } from "./KaraokeText";

const words = ["One", "two", "three"];

describe("KaraokeText", () => {
  test("marks exactly the word at activeIndex as active", () => {
    render(<KaraokeText words={words} activeIndex={1} onWordClick={vi.fn()} />);
    const active = words.map((w) => screen.getByText(w)).filter((el) => el.getAttribute("data-active") === "true");
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveAttribute("data-word-index", "1");
  });

  test("marks no word active when activeIndex is null", () => {
    render(<KaraokeText words={words} activeIndex={null} onWordClick={vi.fn()} />);
    const active = words.map((w) => screen.getByText(w)).filter((el) => el.getAttribute("data-active") === "true");
    expect(active).toHaveLength(0);
  });

  test("clicking a word reports its index", async () => {
    const onWordClick = vi.fn();
    render(<KaraokeText words={words} activeIndex={null} onWordClick={onWordClick} />);
    await userEvent.click(screen.getByText("three"));
    expect(onWordClick).toHaveBeenCalledWith(2);
  });
});
