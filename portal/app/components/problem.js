export default function Problem({ error }) {
  return error ? <div className="notice error" role="alert">
    <strong>{error.status === 401 ? "Sign-in required. " : error.status === 403 ? "Access denied. " : ""}</strong>
    {error.message}
    {error.requestId && <small>Request reference: {error.requestId}</small>}
  </div> : null;
}

