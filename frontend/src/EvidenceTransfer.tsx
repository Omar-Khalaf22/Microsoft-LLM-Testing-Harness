import { useRef, useState } from "react";
import { exportEvidence, importEvidence } from "./api";

// Shown under the "Execution: ..." status of an opened run result.
export function ExportRunButton({ runId }: { runId: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function download() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const evidence = await exportEvidence(runId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = `evidence-${runId}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage("Evidence exported, including related execution and rerun evidence.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Export failed."); }
    finally { setBusy(false); }
  }
  return <div className="export-run" aria-busy={busy}>
    <button className="secondary-button" type="button" disabled={busy} onClick={() => void download()}>Export Run</button>
    {message && <p role="status" className="muted">{message}</p>}
  </div>;
}

export default function EvidenceTransfer({ onImported }: { onImported: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function upload(file?: File) {
    if (!file || busy) return;
    setBusy(true); setMessage("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("Choose an evidence file under 20 MiB.");
      const result = await importEvidence(JSON.parse(await file.text()));
      setMessage(`Imported ${result.imported_run_ids.length} runs.`); onImported();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Import failed."); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  }
  return <div className="panel evidence-transfer" aria-busy={busy}>
    <button className="secondary-button" type="button" disabled={busy} onClick={() => input.current?.click()}>Import Evidence JSON</button>
    <input ref={input} type="file" accept="application/json,.json" hidden onChange={e => void upload(e.target.files?.[0])} />
    <p className="muted">Import preserves evidence and rejects existing run IDs.</p>
    {message && <p role="status">{message}</p>}
  </div>;
}
