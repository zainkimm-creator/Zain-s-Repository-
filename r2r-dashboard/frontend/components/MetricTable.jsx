function formatValue(value) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value);
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.001) return value.toExponential(3);
    return value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

const HIDDEN_KEYS = new Set([
  'source',
  'path',
  'url',
  'file',
  'file_name',
  'filename',
  'paper_reference_file',
  'local_path',
]);

function isDisplayKey(key) {
  const normalized = String(key).toLowerCase();
  if (HIDDEN_KEYS.has(normalized)) return false;
  if (normalized.endsWith('_path') || normalized.endsWith('_url') || normalized.endsWith('_file')) return false;
  if (normalized.includes('reference_file') || normalized.includes('local_path')) return false;
  return true;
}

export default function MetricTable({ rows }) {
  if (!rows) return null;

  if (!Array.isArray(rows)) {
    const entries = Object.entries(rows).filter(([key]) => isDisplayKey(key));
    if (entries.length === 0) return null;
    return (
      <table className="data-table">
        <tbody>
          {entries.map(([key, value]) => (
            <tr key={key}>
              <th>{key}</th>
              <td>{formatValue(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (rows.length === 0) return null;
  const columns = Object.keys(rows[0]).filter(isDisplayKey);
  if (columns.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${index}-${JSON.stringify(row).slice(0, 12)}`}>
              {columns.map((column) => (
                <td key={column}>{formatValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
