import type { OutputFile } from "@/domain/events";
import { api, isLive } from "@/services/api";
import { toast } from "@/store/uiStore";
import { Pill } from "../ui/Pill";

/** File name, Checked pill, pages, sources, Download. */
export function OutputCard({ file }: { file: OutputFile }) {
  return (
    <div className="card green">
      <div className="row">
        <span className="strong">{file.name}</span>
        <Pill tone={file.checked ? "green" : "warn"}>{file.checked ? "Checked" : "Needs review"}</Pill>
        <span className="hint">{file.pages} {file.pages === 1 ? "page" : "pages"} · {file.sources} sources</span>
        <div className="grow" />
        {isLive && file.id ? (
          <a className="btn small" href={api.artifactUrl(file.id)} download={file.name}>Download</a>
        ) : (
          <button type="button" className="btn small" onClick={() => toast("Download started (demo)")}>Download</button>
        )}
      </div>
      {file.warning && <span className="hint warn">{file.warning}</span>}
    </div>
  );
}
