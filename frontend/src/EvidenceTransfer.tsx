import { useRef, useState } from "react";
import { exportEvidence, importEvidence } from "./api";

export default function EvidenceTransfer({ selectedRunId, onImported }: {
  selectedRunId?: string; onImported: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function download() {
    if (!selectedRunId || busy) return;
    setBusy(true); setMessage("");
    try {
      const evidence = await exportEvidence(selectedRunId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = `evidence-${selectedRunId}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage("Evidence exported, including related execution and rerun evidence.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Export failed."); }
    finally { setBusy(false); }
  }
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
    <button className="secondary-button" type="button" disabled={busy || !selectedRunId} onClick={() => void download()}>Export opened run</button>{" "}
    <button className="secondary-button" type="button" disabled={busy} onClick={() => input.current?.click()}>Import evidence JSON</button>
    <input ref={input} type="file" accept="application/json,.json" hidden onChange={e => void upload(e.target.files?.[0])} />
    <p className="muted">Import preserves evidence and rejects existing run IDs.</p>
    {message && <p role="status">{message}</p>}
  </div>;
}
