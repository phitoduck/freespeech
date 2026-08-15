import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DropZone } from "./DropZone";

function makeFile() {
  return new File(["dummy"], "doc.pdf", { type: "application/pdf" });
}

describe("DropZone", () => {
  test("dropping a file calls onFile with that file", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    const file = makeFile();
    fireEvent.drop(screen.getByText("Drop a PDF here"), {
      dataTransfer: { files: [file], types: ["Files"] },
    });
    expect(onFile).toHaveBeenCalledWith(file);
  });

  test("dragging over without dropping does not call onFile", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    fireEvent.dragOver(screen.getByText("Drop a PDF here"), {
      dataTransfer: { files: [], types: ["Files"] },
    });
    expect(onFile).not.toHaveBeenCalled();
  });

  test("drag-over state is set while dragging and cleared on leave", () => {
    render(<DropZone onFile={vi.fn()} />);
    const zone = screen.getByText("Drop a PDF here").closest("[data-dragging]") as HTMLElement;
    fireEvent.dragOver(zone, { dataTransfer: { files: [], types: ["Files"] } });
    expect(zone).toHaveAttribute("data-dragging", "true");
    fireEvent.dragLeave(zone);
    expect(zone).toHaveAttribute("data-dragging", "false");
  });

  test("shows the error as an alert when set, and no alert otherwise", () => {
    const { rerender } = render(<DropZone onFile={vi.fn()} />);
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(<DropZone onFile={vi.fn()} error="Only PDF files are supported" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Only PDF files are supported");
  });

  test("choosing a file through the hidden file input calls onFile with that file", () => {
    const onFile = vi.fn();
    const { container } = render(<DropZone onFile={onFile} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFile).toHaveBeenCalledWith(file);
  });

  test("activating the drop zone opens the file picker", () => {
    const { container } = render(<DropZone onFile={vi.fn()} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, "click");
    fireEvent.click(screen.getByText("Drop a PDF here"));
    expect(clickSpy).toHaveBeenCalled();
  });
});
