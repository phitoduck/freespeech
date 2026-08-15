import { useEffect, useRef, useState, type JSX } from "react";
import { DropZone } from "./components/DropZone";
import { KaraokeText } from "./components/KaraokeText";
import { activeIndex, type Span } from "./lib/timeline";

// Only the fields this app reads. The API also returns each word's bounding box
// and the page dimensions, which a positioned-overlay renderer would need — this
// one flows the words as text, so they are deliberately not modelled here.
interface Page {
  index: number;
  words: { text: string }[];
}

// Only the fields this app reads, to navigate pages: id (to fetch any page's narration) + page count.
interface Doc {
  id: string;
  pageCount: number;
  pages: Page[];
}

interface Narration {
  audioUrl: string;
  spans: Span[];
}

// Seconds to seek past a span's start: the browser can snap audio.currentTime
// down to a frame boundary just before the requested time, which would make
// activeIndex resolve to the previous word instead of the one clicked.
const SEEK_EPSILON = 0.01;

/** Root app: drop a PDF, then play its narration with the spoken word highlighted. */
export function App(): JSX.Element {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [pageIndex, setPageIndex] = useState<number | null>(null);
  const [narration, setNarration] = useState<Narration | null>(null);
  const [status, setStatus] = useState<"" | "Uploading…" | "Preparing narration…">("");
  const [error, setError] = useState<string | undefined>(undefined);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeWordIndex, setActiveWordIndex] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  // Bumped on every loadPage call so a response from a superseded request
  // (an earlier page, or a document swapped out from under it) can be told
  // apart from the one still expected, however that request was triggered.
  const requestIdRef = useRef(0);

  // Derived, not its own state slot, so it can't drift out of sync with doc.
  const page = doc && pageIndex !== null ? doc.pages[pageIndex] : null;

  // Drive the highlight from audio.currentTime, one rAF loop for the life of the narration.
  useEffect(() => {
    if (!narration) return;
    let raf: number;
    const tick = () => {
      const audio = audioRef.current;
      if (audio) {
        const spanIdx = activeIndex(narration.spans, audio.currentTime);
        const wordIdx = spanIdx === null ? null : narration.spans[spanIdx].wordIndex;
        setActiveWordIndex((prev) => (prev === wordIdx ? prev : wordIdx));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [narration]);

  /**
   * Fetch a page's narration and make it the one being read, resetting playback
   * state so no stale highlight or audio carries over from the previous page.
   *
   * @example
   * // loadPage("ab12cd34ef56", 1)
   * // -> GET /api/documents/ab12cd34ef56/pages/1/narration?voice=am_adam
   * // -> setPageIndex(1); setNarration({ audioUrl, spans })
   */
  async function loadPage(docId: string, index: number) {
    const requestId = ++requestIdRef.current;
    setPageIndex(index);
    setIsPlaying(false);
    setActiveWordIndex(null);
    setNarration(null);
    setStatus("Preparing narration…");
    try {
      const narrRes = await fetch(`/api/documents/${docId}/pages/${index}/narration?voice=am_adam`);
      if (!narrRes.ok) throw new Error("narration failed");
      const narr = await narrRes.json();
      // A newer loadPage call (another page, or a freshly dropped document)
      // may have started since this fetch went out. If so, this response is
      // stale — applying it would overwrite the page the reader is now on.
      if (requestIdRef.current !== requestId) return;
      setNarration({
        audioUrl: narr.audio_url,
        spans: narr.spans.map((s: { word_index: number; start: number; end: number }) => ({
          wordIndex: s.word_index,
          start: s.start,
          end: s.end,
        })),
      });
    } catch {
      if (requestIdRef.current === requestId) setError("Something went wrong while reading that PDF");
    } finally {
      if (requestIdRef.current === requestId) setStatus("");
    }
  }

  async function handleFile(file: File) {
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setError("Only PDF files are supported");
      return;
    }
    setError(undefined);
    setDoc(null);
    setPageIndex(null);
    setNarration(null);
    setStatus("Uploading…");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/documents", { method: "POST", body: form });
      if (res.status === 400) {
        setError((await res.json()).detail);
        return;
      }
      if (!res.ok) throw new Error("upload failed");
      const body = await res.json();
      const newDoc: Doc = { id: body.id, pageCount: body.page_count, pages: body.pages };
      setDoc(newDoc);
      await loadPage(newDoc.id, 0);
    } catch {
      setError("Something went wrong while reading that PDF");
      setDoc(null);
      setPageIndex(null);
    } finally {
      setStatus("");
    }
  }

  /**
   * Jump to a page by index, loading its narration; out-of-range indices are ignored.
   *
   * @example
   * // doc.pageCount === 3; goToPage(1) -> loadPage(doc.id, 1)
   * // goToPage(3) -> no-op (out of range)
   */
  function goToPage(index: number) {
    if (!doc?.pages[index]) return;
    void loadPage(doc.id, index);
  }

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play();
    else audio.pause();
  }

  function handleWordClick(i: number) {
    const audio = audioRef.current;
    const span = narration?.spans.find((s) => s.wordIndex === i);
    if (!audio || !span) return;
    audio.currentTime = span.start + Math.min(SEEK_EPSILON, (span.end - span.start) / 2);
  }

  return (
    <main className="app">
      <h1>Karaoke PDF Reader</h1>
      <div data-testid="status" className="status">
        {status}
      </div>
      {!page ? (
        <DropZone onFile={handleFile} error={error} />
      ) : (
        <div className="reader" data-testid="page-view">
          <button data-testid="play-button" className="pill-button play-button" onClick={togglePlay} disabled={!narration}>
            {isPlaying ? "Pause" : "Play"}
          </button>
          <KaraokeText
            words={page.words.map((w) => w.text)}
            activeIndex={activeWordIndex}
            onWordClick={handleWordClick}
          />
          {narration && (
            <audio
              ref={audioRef}
              src={narration.audioUrl}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
            />
          )}
          {doc && doc.pageCount > 1 && (
            <div className="page-controls" data-testid="page-controls">
              <button data-testid="previous-page" className="pill-button" onClick={() => goToPage(page.index - 1)} disabled={page.index === 0}>
                Previous
              </button>
              <span>
                Page {page.index + 1} of {doc.pageCount}
              </span>
              <button data-testid="next-page" className="pill-button" onClick={() => goToPage(page.index + 1)} disabled={page.index === doc.pageCount - 1}>
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
