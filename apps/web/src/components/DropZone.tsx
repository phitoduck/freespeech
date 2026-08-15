import { useRef, useState, type ChangeEvent, type DragEvent, type JSX } from "react";

export interface DropZoneProps {
  /** Called with the chosen or dropped file, whatever its type — the caller validates it. */
  onFile: (f: File) => void;
  /** Message to show as an alert, e.g. when the last dropped file was rejected. */
  error?: string;
}

/**
 * A drag-and-drop and click-to-browse target for a single file.
 *
 * @example
 * <DropZone onFile={(f) => upload(f)} error={uploadError} />
 */
export function DropZone({ onFile, error }: DropZoneProps): JSX.Element {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      className="drop-zone"
      data-testid="drop-zone"
      data-dragging={dragging}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <p>Drop a PDF here</p>
      {error && <p role="alert">{error}</p>}
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="visually-hidden"
        onChange={handleChange}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
