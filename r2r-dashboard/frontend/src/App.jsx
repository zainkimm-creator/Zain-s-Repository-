import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  Factory,
  Gauge,
  GitCompare,
  LineChart,
  ListChecks,
  RefreshCw,
  Settings2,
  Sigma,
  SlidersHorizontal,
  Waves,
} from 'lucide-react';
import ResultPanel from '../components/ResultPanel.jsx';
import RunButton from '../components/RunButton.jsx';
import MetricTable from '../components/MetricTable.jsx';
import R2RSchematic from '../components/R2RSchematic.jsx';
import { DEFAULT_API_BASE, apiGet, apiPost } from './api.js';

const PAGES = [
  { id: 'simulation', label: 'Simulation', icon: Waves },
  { id: 'parts', label: 'Paper parts', icon: ListChecks },
  { id: 'plants', label: 'Plants', icon: Factory },
  { id: 'sysid', label: 'SysID', icon: Sigma },
  { id: 'logging', label: 'Logging rate', icon: LineChart },
  { id: 'excitation', label: 'Excitation', icon: BarChart3 },
  { id: 'drift', label: 'Drift', icon: GitCompare },
  { id: 'retuning', label: 'Retuning', icon: SlidersHorizontal },
  { id: 'equations', label: 'Equations', icon: Settings2 },
];

function Field({ label, value, onChange, type = 'number', step = '0.01' }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={value} step={step} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectField({ label, value, onChange, options }) {
  const normalizedOptions = options.map((option) =>
    typeof option === 'string' ? { value: option, label: option } : option,
  );
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {normalizedOptions.map((option) => (
          <option value={option.value} key={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PlantPage({ plants, selectedPlantId, onSelect }) {
  const selectedPlant = plants.find((plant) => plant.plant_id === selectedPlantId) ?? plants[0];
  const options = plants.map((plant) => ({ value: plant.plant_id, label: plant.label }));
  if (!selectedPlant) {
    return <section className="panel empty-panel">No plant data loaded.</section>;
  }

  const selectedSummary = {
    plant_id: selectedPlant.plant_id,
    material: selectedPlant.material,
    scale: selectedPlant.scale,
    regime: selectedPlant.regime,
    EA_N: selectedPlant.EA_N,
    zeta_cl_min: selectedPlant.zeta_cl_min,
    overshoot_percent: selectedPlant.overshoot_percent,
  };

  const selectedParameters = {
    EA_N: selectedPlant.EA_N,
    recommended_excitation_amplitude_V: selectedPlant.recommended_excitation_amplitude_V,
    baseline_range_compatible: selectedPlant.baseline_range_compatible,
    roller_radius_m: selectedPlant.roller_radius_m?.join(', '),
    span_length_m: selectedPlant.span_length_m?.join(', '),
    inertia_kg_m2: selectedPlant.inertia_kg_m2?.join(', '),
    viscous_friction: selectedPlant.viscous_friction?.join(', '),
    process_noise_b: selectedPlant.process_noise_b,
  };

  return (
    <section className="plant-layout">
      <div className="panel controls-panel compact-controls">
        <SelectField label="Selected plant" value={selectedPlant.plant_id} options={options} onChange={onSelect} />
        <p className="plant-note">
          The selected plant is sent to Simulation, SysID, Paper parts, Logging rate, Excitation, Drift, and Retuning.
        </p>
      </div>
      <div className="panel plant-panel">
        <div className="plant-heading">
          <div>
            <h2>{selectedPlant.label}</h2>
            <span>Supplement Table S12 plant preset</span>
          </div>
        </div>
        <div className="plant-detail-grid">
          <MetricTable rows={selectedSummary} />
          <MetricTable rows={selectedParameters} />
        </div>
        <p className="plant-note">
          Current extracted supplement data gives plant-specific `EA_N` and plant metadata. The PDF states that exact
          per-roller `R`, `J`, `f`, `L`, and `b` arrays exist, but those arrays are not present in the extracted JSON, so
          the simulator keeps the current baseline arrays until the exact arrays are supplied. High-EA plants outside the
          extracted baseline range use zero excitation by default to keep the paper-equation simulation bounded.
        </p>
        <h2>All Plants</h2>
        <MetricTable rows={plants} />
      </div>
    </section>
  );
}

function ErrorBanner({ message }) {
  if (!message) return null;
  return <div className="error-banner">{message}</div>;
}

const TIME_SCALE_ROWS = [
  { time: 'Every 1 ms', event: 'RK4 calculates new tension/speed from equations' },
  { time: 'Every 10 ms', event: 'PI controller updates motor torque u' },
  { time: 'Between 10 ms updates', event: 'Same u is held constant by ZOH' },
  { time: 'Every Tlog, e.g. 20 ms', event: 'PLC saves tension/speed data for SysID' },
];

const EXCITATION_INFO_ROWS = [
  {
    excitation: 'ET1',
    type: 'single-channel sine',
    channels: 'UW only',
    changing_factors: '0.70 Hz sine on u_UW; u_Nip and u_RW are zero.',
  },
  {
    excitation: 'ET3',
    type: 'three-channel sine',
    channels: 'UW, Nip, RW',
    changing_factors: '0.55, 0.80, and 1.10 Hz sine waves with phase offsets.',
  },
  {
    excitation: 'ET6',
    type: 'three-channel multi-sine',
    channels: 'UW, Nip, RW',
    changing_factors: 'Two sine components per motor input; richer frequency content than ET3.',
  },
  {
    excitation: 'E_Toggle',
    type: 'three-channel square/toggle',
    channels: 'UW, Nip, RW',
    changing_factors: 'Square waves with staggered 0.42, 0.58, and 0.74 s periods.',
  },
  {
    excitation: 'EVR',
    type: 'event-varying random',
    channels: 'UW, Nip, RW',
    changing_factors: 'Random held voltage values updated in 0.15 s buckets.',
  },
];

const EQUATION_TABS = [
  { id: 'equations', label: 'Equations' },
  { id: 'time-scales', label: 'Time scales' },
  { id: 'excitation-info', label: 'Excitation info' },
];

function EquationTabs({ activeTab, onSelect }) {
  return (
    <div className="subtab-row" role="tablist" aria-label="Equation section tabs">
      {EQUATION_TABS.map((tab) => (
        <button
          className={activeTab === tab.id ? 'active' : ''}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          onClick={() => onSelect(tab.id)}
          key={tab.id}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function TimeScalesPage() {
  return (
    <section className="equation-layout">
      <div className="panel equation-panel equation-wide">
        <h2>Time Scales</h2>
        <p>
          In simple words: the physical machine is simulated every 1 ms, the controller changes its command every 10 ms,
          and the PLC may save data every 10-100 ms.
        </p>
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>Example</h2>
        <MetricTable rows={TIME_SCALE_ROWS} />
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>Controller Action Example</h2>
        <p>
          So if Ts = 10 ms and dt = 1 ms, then one controller action contains 10 small physics calculations.
        </p>
        <ol className="derivation-list">
          <li>0 ms: controller updates u.</li>
          <li>1-9 ms: RK4 keeps calculating physics with same u.</li>
          <li>10 ms: controller updates u again.</li>
          <li>20 ms: if Tlog = 20 ms, PLC records data.</li>
        </ol>
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>Concise Meaning</h2>
        <p>
          RK4 is the fast physics calculator, PI controller is slower, and PLC logging may be even slower or different,
          which affects SysID accuracy.
        </p>
      </div>
    </section>
  );
}

function ExcitationInfoPage() {
  return (
    <section className="equation-layout">
      <div className="panel equation-panel equation-wide">
        <h2>Excitation Information</h2>
        <p>
          These excitation profiles define which motor inputs are disturbed and what waveform is used. Changing the
          excitation changes the input channels, frequency content, timing, and state motion seen by Simulation and SysID.
        </p>
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>Excitation Table</h2>
        <MetricTable rows={EXCITATION_INFO_ROWS} />
      </div>
    </section>
  );
}

function MergedEquationsPage({ equations }) {
  const fallbackRegister = [
    ...(equations.paper_equations ?? []).map((item) => ({
      source: 'Paper',
      number: item.number,
      title: item.title,
      equation: item.equation,
      variables: item.variables,
      usage: item.paper_use,
      dashboard_note: item.dashboard_note,
    })),
    ...(equations.backend_equations ?? []).map((item) => ({
      source: 'System',
      number: 'backend',
      title: item.title,
      equation: item.equation,
      variables: item.variables,
      usage: item.backend_use,
      dashboard_note: 'This is a runnable backend equation used by the current dashboard model.',
    })),
  ];
  const register = equations.equation_register ?? fallbackRegister;

  return (
    <section className="equation-layout">
      <div className="panel equation-panel equation-wide">
        <h2>Basic Theory</h2>
        <p>{equations.section2_note}</p>
        <div className="theory-grid">
          {equations.theory_summary?.map((item) => (
            <article className="theory-card" key={item.title}>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>State / Input / Output</h2>
        <div className="equation-group-grid">
          <p className="formula">{equations.state_vector}</p>
          <p className="formula">{equations.input_vector}</p>
          <p className="formula">{equations.output_vector}</p>
        </div>
      </div>
      <div className="panel equation-panel equation-wide">
        <h2>Merged Equation Register</h2>
        <div className="paper-equation-grid">
          {register.map((item) => (
            <article className="paper-equation-card" key={`${item.source}-${item.number}-${item.title}`}>
              <div className="paper-equation-header">
                <span>{item.source}</span>
                <span>{item.number}</span>
                <strong>{item.title}</strong>
              </div>
              <p className="formula paper-formula">{item.equation}</p>
              <p className="equation-note">{item.variables}</p>
              <p className="equation-note">{item.usage}</p>
              <p className="equation-note">{item.dashboard_note}</p>
            </article>
          ))}
        </div>
      </div>
      <div className="panel equation-panel">
        <h2>Tension Dynamics</h2>
        {equations.tension_dynamics.map((item) => (
          <p className="formula" key={item}>
            {item}
          </p>
        ))}
      </div>
      <div className="panel equation-panel">
        <h2>Roller Velocity Dynamics</h2>
        {equations.roller_velocity_dynamics.map((item) => (
          <p className="formula" key={item}>
            {item}
          </p>
        ))}
      </div>
      <div className="panel equation-panel">
        <h2>Units</h2>
        <MetricTable rows={equations.units} />
      </div>
      <div className="panel equation-panel">
        <h2>Derivation / Usage Flow</h2>
        <ol className="derivation-list">
          {equations.derivation_steps?.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function EquationPage({ equations }) {
  const [activeEquationTab, setActiveEquationTab] = useState('equations');

  if (!equations) return <section className="panel empty-panel">No equation data loaded.</section>;

  let content = <MergedEquationsPage equations={equations} />;
  if (activeEquationTab === 'time-scales') content = <TimeScalesPage />;
  if (activeEquationTab === 'excitation-info') content = <ExcitationInfoPage />;

  return (
    <>
      <EquationTabs activeTab={activeEquationTab} onSelect={setActiveEquationTab} />
      {content}
    </>
  );
}

export default function App() {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_API_BASE);
  const [activePage, setActivePage] = useState('simulation');
  const [status, setStatus] = useState('checking');
  const [metadata, setMetadata] = useState(null);
  const [selectedPlantId, setSelectedPlantId] = useState('P01');
  const [equations, setEquations] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [simForm, setSimForm] = useState({
    duration_s: '4',
    log_sample_time_ms: '10',
    excitation: 'ET3',
    excitation_amplitude_V: '0.08',
    sensor_noise_tension_N: '0',
    sensor_noise_omega_rad_s: '0',
  });
  const [sysidForm, setSysidForm] = useState({
    duration_s: '4',
    log_sample_time_ms: '10',
    excitation: 'E_Toggle',
    excitation_amplitude_V: '0.08',
    sensor_noise_tension_N: '0',
    sensor_noise_omega_rad_s: '0',
  });

  const excitationOptions = useMemo(
    () => metadata?.excitation_profiles ?? ['ET1', 'ET3', 'ET6', 'E_Toggle', 'EVR'],
    [metadata],
  );
  const plantOptions = useMemo(
    () =>
      (metadata?.plants ?? []).map((plant) => ({
        value: plant.plant_id,
        label: plant.label,
      })),
    [metadata],
  );
  const plants = metadata?.plants ?? [];
  const selectedPlant = useMemo(
    () => plants.find((plant) => plant.plant_id === selectedPlantId),
    [plants, selectedPlantId],
  );

  async function refreshMetadata() {
    try {
      setStatus('checking');
      const [health, meta, eq] = await Promise.all([
        apiGet(baseUrl, '/health'),
        apiGet(baseUrl, '/metadata'),
        apiGet(baseUrl, '/equations'),
      ]);
      setStatus(health.status === 'ok' ? 'online' : 'unknown');
      setMetadata(meta);
      if (meta.default_plant_id && !meta.plants?.some((plant) => plant.plant_id === selectedPlantId)) {
        setSelectedPlantId(meta.default_plant_id);
      }
      setEquations(eq);
      setError('');
    } catch (err) {
      setStatus('offline');
      setError(err.message);
    }
  }

  useEffect(() => {
    refreshMetadata();
  }, []);

  async function runRequest(path, body = {}) {
    setLoading(true);
    setError('');
    try {
      const payload = await apiPost(baseUrl, path, body);
      setResult(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function numericForm(form) {
    return Object.fromEntries(
      Object.entries(form).map(([key, value]) => {
        if (key === 'excitation' || key === 'plant_id') return [key, value];
        return [key, Number(value)];
      }),
    );
  }

  function plantBody(body = {}) {
    return { ...body, plant_id: selectedPlantId };
  }

  function handlePlantSelect(plantId) {
    setSelectedPlantId(plantId);
    const plant = plants.find((item) => item.plant_id === plantId);
    if (!plant || plant.recommended_excitation_amplitude_V === undefined) return;
    const amplitude = String(plant.recommended_excitation_amplitude_V);
    setSimForm((current) => ({ ...current, excitation_amplitude_V: amplitude }));
    setSysidForm((current) => ({ ...current, excitation_amplitude_V: amplitude }));
  }

  function renderControls() {
    if (activePage === 'simulation') {
      return (
        <section className="panel controls-panel">
          <div className="field-grid">
            <Field label="Duration (s)" value={simForm.duration_s} onChange={(v) => setSimForm({ ...simForm, duration_s: v })} />
            {plantOptions.length > 0 && <SelectField label="Plant" value={selectedPlantId} options={plantOptions} onChange={handlePlantSelect} />}
            {selectedPlant?.simulation_note && <p className="plant-note">{selectedPlant.simulation_note}</p>}
            <Field label="Tlog (ms)" value={simForm.log_sample_time_ms} onChange={(v) => setSimForm({ ...simForm, log_sample_time_ms: v })} />
            <SelectField label="Excitation" value={simForm.excitation} options={excitationOptions} onChange={(v) => setSimForm({ ...simForm, excitation: v })} />
            <Field label="Amplitude (V)" value={simForm.excitation_amplitude_V} onChange={(v) => setSimForm({ ...simForm, excitation_amplitude_V: v })} />
            <Field label="T noise (N)" value={simForm.sensor_noise_tension_N} onChange={(v) => setSimForm({ ...simForm, sensor_noise_tension_N: v })} />
            <Field label="Omega noise" value={simForm.sensor_noise_omega_rad_s} onChange={(v) => setSimForm({ ...simForm, sensor_noise_omega_rad_s: v })} />
          </div>
          <RunButton loading={loading} onClick={() => runRequest('/simulate', plantBody(numericForm(simForm)))}>Run Simulation</RunButton>
        </section>
      );
    }

    if (activePage === 'sysid') {
      return (
        <section className="panel controls-panel">
          <div className="field-grid">
            <Field label="Duration (s)" value={sysidForm.duration_s} onChange={(v) => setSysidForm({ ...sysidForm, duration_s: v })} />
            {plantOptions.length > 0 && <SelectField label="Plant" value={selectedPlantId} options={plantOptions} onChange={handlePlantSelect} />}
            {selectedPlant?.simulation_note && <p className="plant-note">{selectedPlant.simulation_note}</p>}
            <Field label="Tlog (ms)" value={sysidForm.log_sample_time_ms} onChange={(v) => setSysidForm({ ...sysidForm, log_sample_time_ms: v })} />
            <SelectField label="Excitation" value={sysidForm.excitation} options={excitationOptions} onChange={(v) => setSysidForm({ ...sysidForm, excitation: v })} />
            <Field label="Amplitude (V)" value={sysidForm.excitation_amplitude_V} onChange={(v) => setSysidForm({ ...sysidForm, excitation_amplitude_V: v })} />
            <Field label="T noise (N)" value={sysidForm.sensor_noise_tension_N} onChange={(v) => setSysidForm({ ...sysidForm, sensor_noise_tension_N: v })} />
            <Field label="Omega noise" value={sysidForm.sensor_noise_omega_rad_s} onChange={(v) => setSysidForm({ ...sysidForm, sensor_noise_omega_rad_s: v })} />
          </div>
          <RunButton loading={loading} onClick={() => runRequest('/sysid', plantBody(numericForm(sysidForm)))}>Run SysID</RunButton>
        </section>
      );
    }

    const validationRoutes = {
      parts: ['/validate/part/1', 'Run Part 1'],
      logging: ['/validate/logging-rate', 'Run Logging Sweep'],
      excitation: ['/validate/excitation', 'Run Excitation Study'],
      drift: ['/validate/drift', 'Run Drift Study'],
      retuning: ['/retune', 'Run Retuning'],
    };
    if (validationRoutes[activePage]) {
      const [path, label] = validationRoutes[activePage];
      return (
        <section className="panel controls-panel compact-controls">
          <RunButton loading={loading} onClick={() => runRequest(path, plantBody())}>{label}</RunButton>
        </section>
      );
    }
    return null;
  }

  const ActiveIcon = PAGES.find((page) => page.id === activePage)?.icon ?? Activity;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <Gauge size={26} />
          <div>
            <strong>R2R SysID</strong>
            <span>Validation</span>
          </div>
        </div>
        <nav className="page-nav">
          {PAGES.map(({ id, label, icon: Icon }) => (
            <button className={activePage === id ? 'active' : ''} type="button" onClick={() => setActivePage(id)} key={id}>
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="title-block">
            <ActiveIcon size={24} />
            <div>
              <h1>{PAGES.find((page) => page.id === activePage)?.label}</h1>
              <span className={`status-pill ${status}`}>{status}</span>
            </div>
          </div>
          <div className="api-controls">
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} aria-label="API base URL" />
            <button className="icon-button" type="button" onClick={refreshMetadata} title="Refresh API status">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        <ErrorBanner message={error} />

        {activePage === 'equations' ? (
          <EquationPage equations={equations} />
        ) : activePage === 'plants' ? (
          <PlantPage plants={plants} selectedPlantId={selectedPlantId} onSelect={handlePlantSelect} />
        ) : activePage === 'simulation' ? (
          <div className="simulation-page">
            <R2RSchematic />
            <div className="work-grid">
              {renderControls()}
              <ResultPanel baseUrl={baseUrl} result={result} />
            </div>
          </div>
        ) : (
          <div className="work-grid">
            {renderControls()}
            <ResultPanel baseUrl={baseUrl} result={result} />
          </div>
        )}
      </main>
    </div>
  );
}
