"use client";

import { useEffect, useRef, useState } from "react";
import Problem from "./problem";

const ACCEPT = { csv: ".csv", zip: ".zip", tar_gz: ".tar.gz,.tgz" };

export default function Datasets({ api, project, onUploadingChange }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(Boolean(project));
  const [loadError, setLoadError] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [datasetId, setDatasetId] = useState("");
  const [version, setVersion] = useState(1);
  const [versionData, setVersionData] = useState(null);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionError, setVersionError] = useState(null);
  const [versionRefresh, setVersionRefresh] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [format, setFormat] = useState("csv");
  const [file, setFile] = useState(null);
  const [versionFile, setVersionFile] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [uploadError, setUploadError] = useState(null);
  const [newVersionError, setNewVersionError] = useState(null);
  const [message, setMessage] = useState("");
  const uploadInput = useRef(null);
  const versionInput = useRef(null);
  const retry = useRef({});
  const uploadRequest = useRef(null);
  const busyRef = useRef(false);
  const dataset = items.find((item) => item.dataset_id === datasetId);

  useEffect(() => () => uploadRequest.current?.abort(), []);

  useEffect(() => {
    if (!project) return;
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    api.listDatasets(project.project_id, controller.signal).then((body) => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(body.items)) throw new Error("The dataset list could not be read.");
      setItems(body.items);
      setDatasetId((current) => body.items.some((item) => item.dataset_id === current) ? current : "");
    }).catch((error) => {
      if (!controller.signal.aborted) setLoadError(error);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, project?.project_id, refresh]);

  useEffect(() => {
    setVersionData(null);
    setVersionError(null);
    if (!datasetId) return;
    const controller = new AbortController();
    setVersionLoading(true);
    api.getDatasetVersion(datasetId, version, controller.signal).then((body) => {
      if (!controller.signal.aborted) setVersionData(body);
    }).catch((error) => {
      if (!controller.signal.aborted) setVersionError(error);
    }).finally(() => { if (!controller.signal.aborted) setVersionLoading(false); });
    return () => controller.abort();
  }, [api, datasetId, version, versionRefresh]);

  function selectDataset(id) {
    if (id === datasetId) return;
    setDatasetId(id);
    setVersion(items.find((item) => item.dataset_id === id)?.latest_version || 1);
    setVersionData(null);
    setVersionError(null);
    setNewVersionError(null);
    setMessage("");
    setNote("");
    setVersionFile(null);
    if (versionInput.current) versionInput.current.value = "";
  }

  async function upload(event, kind) {
    event.preventDefault();
    if (busyRef.current) return;
    const isNew = kind === "dataset";
    const chosenFile = isNew ? file : versionFile;
    const reportError = isNew ? setUploadError : setNewVersionError;
    reportError(null);
    setMessage("");
    if (!chosenFile || (isNew && !name.trim())) {
      reportError(new Error(isNew ? "Enter a dataset name and choose a file." : "Choose a file for this version."));
      return;
    }
    const metadata = isNew ? JSON.stringify([project.project_id, name.trim(), description.trim(), format]) : JSON.stringify([datasetId, note.trim()]);
    if (retry.current[kind]?.file !== chosenFile || retry.current[kind]?.metadata !== metadata) {
      retry.current[kind] = { file: chosenFile, metadata, key: crypto.randomUUID() };
    }
    const form = new FormData();
    form.set("file", chosenFile);
    if (isNew) {
      form.set("project_id", project.project_id);
      form.set("name", name.trim());
      form.set("format", format);
      if (description.trim()) form.set("description", description.trim());
    } else if (note.trim()) form.set("note", note.trim());
    const controller = new AbortController();
    uploadRequest.current = controller;
    busyRef.current = true;
    setBusy(kind);
    onUploadingChange?.(true);
    try {
      if (isNew) {
        const created = await api.uploadDataset(form, retry.current[kind].key, controller.signal);
        if (controller.signal.aborted) return;
        setItems((old) => [...old.filter((item) => item.dataset_id !== created.dataset_id), created]);
        setDatasetId(created.dataset_id);
        setVersion(created.latest_version);
        setVersionData(null);
        setName("");
        setDescription("");
        setFile(null);
        uploadInput.current.value = "";
        setMessage(`Uploaded ${created.name}. Version ${created.latest_version} is selected.`);
      } else {
        const created = await api.uploadDatasetVersion(datasetId, form, retry.current[kind].key, controller.signal);
        if (controller.signal.aborted) return;
        setItems((old) => old.map((item) => item.dataset_id === datasetId ? { ...item, latest_version: Math.max(item.latest_version, created.version) } : item));
        setVersion(created.version);
        setVersionData(null);
        setVersionRefresh((value) => value + 1);
        setVersionFile(null);
        setNote("");
        versionInput.current.value = "";
        setMessage(`Uploaded version ${created.version} of ${dataset.name}.`);
      }
      delete retry.current[kind];
    } catch (error) {
      if (!controller.signal.aborted) reportError(error);
    } finally {
      busyRef.current = false;
      onUploadingChange?.(false);
      if (!controller.signal.aborted) setBusy("");
    }
  }

  return <section id="datasets" aria-labelledby="datasets-title">
    <div className="section-heading"><div><p className="eyebrow">TRAINING DATA</p><h2 id="datasets-title">Datasets</h2></div></div>
    {!project ? <div className="panel"><p className="muted">Select a project to upload datasets and choose a version.</p></div> : <>
      <p className="muted">Datasets for <strong>{project.name}</strong>. Each version fixes the exact data used for a training run.</p>
      <div className="workspace-grid">
        <section className="panel" aria-labelledby="dataset-list-title">
          <div className="section-heading"><h3 id="dataset-list-title">Project datasets</h3>
            <button className="secondary" disabled={loading || Boolean(busy)} onClick={() => setRefresh((value) => value + 1)}>Refresh datasets</button></div>
          <Problem error={loadError} />
          {loading ? <p role="status">Loading datasets…</p> : loadError ? <p>Refresh datasets to try again.</p> : items.length === 0 ? <p className="empty">No datasets yet. Upload your first file.</p> :
            <ul className="project-list">{items.map((item) => <li key={item.dataset_id}>
              <button className={`project-card ${datasetId === item.dataset_id ? "selected" : ""}`} aria-pressed={datasetId === item.dataset_id}
                disabled={Boolean(busy)} onClick={() => selectDataset(item.dataset_id)}>
                <strong>{item.name}</strong><span>{item.format.toUpperCase()} · Latest version {item.latest_version}</span><small>{item.dataset_id}</small>
              </button>
            </li>)}</ul>}
        </section>
        <section className="panel" aria-labelledby="upload-title"><h3 id="upload-title">Upload a dataset</h3>
          <form onSubmit={(event) => upload(event, "dataset")}>
            <fieldset disabled={Boolean(busy) || loading}>
              <label htmlFor="dataset-name">Dataset name *</label>
              <input id="dataset-name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
              <label htmlFor="dataset-description">Dataset description (optional)</label>
              <textarea id="dataset-description" maxLength={1000} rows={2} value={description} onChange={(event) => setDescription(event.target.value)} />
              <label htmlFor="dataset-format">File format</label>
              <select id="dataset-format" value={format} onChange={(event) => setFormat(event.target.value)}>
                <option value="csv">CSV — tabular data</option><option value="zip">ZIP — image folders</option><option value="tar_gz">TAR.GZ — image folders</option>
              </select>
              <label htmlFor="dataset-file">Dataset file *</label>
              <input id="dataset-file" ref={uploadInput} type="file" required accept={ACCEPT[format]} onChange={(event) => setFile(event.target.files[0] || null)} aria-describedby="file-help" />
              <p id="file-help" className="muted">Choose a file matching the selected format. CloudTrain checks its contents.</p>
              <button type="submit">{busy === "dataset" ? "Uploading dataset…" : "Upload dataset"}</button>
            </fieldset>
            <Problem error={uploadError} />
          </form>
        </section>
      </div>
      <p className="success" role="status">{message}</p>
      {dataset && <div className="workspace-grid">
        <section className="panel" aria-labelledby="version-title"><p className="eyebrow">SELECTED DATASET</p><h3 id="version-title">{dataset.name}</h3>
          <p className="muted">{dataset.description || "No description provided."}</p>
          <label htmlFor="dataset-version">Dataset version</label>
          <select id="dataset-version" disabled={Boolean(busy)} value={version} onChange={(event) => { setVersion(Number(event.target.value)); setVersionData(null); }}>
            {Array.from({ length: dataset.latest_version }, (_, index) => index + 1).map((number) => <option key={number} value={number}>Version {number}</option>)}
          </select>
          {versionLoading && <p role="status">Loading version…</p>}
          <Problem error={versionError} />
          {versionError && <button className="secondary" onClick={() => setVersionRefresh((value) => value + 1)}>Retry version</button>}
          {versionData && <div data-testid="version-details"><p className="notice">Selected: {versionData.dataset_id}, version {versionData.version}</p>
            <dl className="metadata"><dt>File size</dt><dd>{new Intl.NumberFormat().format(versionData.size_bytes)} bytes</dd>
              <dt>SHA-256 checksum</dt><dd><code>{versionData.checksum_sha256}</code></dd>
              <dt>Uploaded</dt><dd><time dateTime={versionData.created_at}>{new Date(versionData.created_at).toLocaleString()}</time></dd>
              {versionData.note && <><dt>Version note</dt><dd>{versionData.note}</dd></>}
            </dl>
          </div>}
        </section>
        <section className="panel" aria-labelledby="new-version-title"><h3 id="new-version-title">Upload a new version</h3>
          <p className="muted">Keep the same dataset and add updated data in {dataset.format.toUpperCase()} format.</p>
          <form onSubmit={(event) => upload(event, "version")}>
            <fieldset disabled={Boolean(busy) || loading}>
              <label htmlFor="version-note">Version note (optional)</label>
              <textarea id="version-note" rows={2} maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
              <label htmlFor="version-file">New version file *</label>
              <input id="version-file" ref={versionInput} type="file" required accept={ACCEPT[dataset.format]} onChange={(event) => setVersionFile(event.target.files[0] || null)} />
              <button className="version-submit" type="submit">{busy === "version" ? "Uploading version…" : "Upload version"}</button>
            </fieldset>
            <Problem error={newVersionError} />
          </form>
        </section>
      </div>}
    </>}
  </section>;
}
