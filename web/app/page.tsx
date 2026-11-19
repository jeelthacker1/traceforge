"use client";
import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  Download,
  FlaskConical,
  Layers3,
  LogOut,
  Network,
  Pause,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Shield,
  Terminal,
  TriangleAlert,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  API,
  api,
  type Alert,
  type Detail,
  type Event,
  type GraphData,
  type Incident,
  type Overview,
  type Rule,
} from "@/lib/api";
import { useStore } from "@/lib/store";
const ServiceGraph = dynamic(() => import("@/components/graph"), {
  ssr: false,
});
const navigation = [
  ["Overview", Activity],
  ["Event explorer", Terminal],
  ["Service graph", Network],
  ["Incidents", Layers3],
  ["Time machine", Clock3],
  ["Detection rules", Settings2],
  ["Scenario lab", FlaskConical],
  ["Audit trail", BookOpen],
] as const;
const emptyGraph: GraphData = {
  nodes: [],
  edges: [],
  missing_parents: 0,
  limitations: "No telemetry yet",
};
function time(value: string) {
  return new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z",
  ).toLocaleTimeString();
}
function Badge({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}

export default function Page() {
  const {
    tab,
    setTab,
    minutes,
    setMinutes,
    service,
    setService,
    search,
    setSearch,
  } = useStore();
  const [user, setUser] = useState<{ username: string; role: string } | null>(
      null,
    ),
    [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [alerts, setAlerts] = useState<Alert[]>([]),
    [incidents, setIncidents] = useState<Incident[]>([]),
    [graph, setGraph] = useState<GraphData>(emptyGraph),
    [rules, setRules] = useState<Rule[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null),
    [selected, setSelected] = useState<Event | null>(null),
    [cursor, setCursor] = useState(0),
    [playing, setPlaying] = useState(false),
    [live, setLive] = useState(false),
    [severity, setSeverity] = useState(""),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState<
      { actor: string; action: string; target: string; timestamp: string }[]
    >([]),
    [scenarios, setScenarios] = useState<
      Record<
        string,
        {
          name: string;
          expected: string[];
          truth: string;
          false_positives: string;
        }
      >
    >({});
  const handleError = (e: unknown) =>
    setError(e instanceof Error ? e.message : "Request failed");
  const refresh = useCallback(async () => {
    if (!user) return;
    const query = `minutes=${minutes}&service=${encodeURIComponent(service)}`;
    try {
      const [o, e, a, i, g, r, s] = await Promise.all([
        api<Overview>("/api/overview?" + query),
        api<{ events: Event[] }>(
          "/api/events?" + query + "&search=" + encodeURIComponent(search),
        ),
        api<Alert[]>("/api/alerts" + (severity ? "?severity=" + severity : "")),
        api<Incident[]>("/api/incidents"),
        api<GraphData>("/api/graph?minutes=" + minutes),
        api<Rule[]>("/api/rules"),
        api<typeof scenarios>("/api/scenarios"),
      ]);
      setOverview(o);
      setEvents(e.events);
      setAlerts(a);
      setIncidents(i);
      setGraph(g);
      setRules(r);
      setScenarios(s);
      setError("");
    } catch (e) {
      handleError(e);
    }
  }, [user, minutes, service, search, severity]);
  useEffect(() => {
    api<{ username: string; role: string }>("/api/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!user) return;
    let ws: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    function connect() {
      ws = new WebSocket(API.replace(/^http/, "ws") + "/ws");
      ws.onopen = () => setLive(true);
      ws.onmessage = (e) => {
        if (JSON.parse(e.data).type === "events") void refresh();
      };
      ws.onerror = () => setLive(false);
      ws.onclose = () => {
        setLive(false);
        if (!stopped) timer = setTimeout(connect, 3000);
      };
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [user, refresh]);
  useEffect(() => {
    if (!playing || !detail) return;
    const timer = setInterval(
      () =>
        setCursor((c) => {
          if (c >= detail.events.length - 1) {
            setPlaying(false);
            return c;
          }
          return c + 1;
        }),
      800,
    );
    return () => clearInterval(timer);
  }, [playing, detail]);
  useEffect(() => {
    if (tab === "Audit trail" && user?.role !== "VIEWER")
      api<typeof audit>("/api/audit").then(setAudit).catch(handleError);
  }, [tab, user]);
  const action = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await fn();
      setNotice(message);
      await refresh();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };
  const openIncident = async (id: string) => {
    try {
      const d = await api<Detail>("/api/incidents/" + id);
      setDetail(d);
      setCursor(0);
      setSelected(null);
      setTab("Time machine");
    } catch (e) {
      handleError(e);
    }
  };
  const pickService = (id: string) => {
    setService(id);
    setTab("Event explorer");
  };
  async function download(format: string) {
    if (!detail) return;
    try {
      const r = await fetch(
        `${API}/api/incidents/${detail.id}/report?format=${format}`,
        { credentials: "include" },
      );
      if (!r.ok) throw new Error("Export failed");
      const u = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = u;
      a.download = detail.id + "." + format;
      a.click();
      URL.revokeObjectURL(u);
    } catch (e) {
      handleError(e);
    }
  }
  if (!ready)
    return (
      <main className="login">
        <ShieldCheck size={42} />
        <p>Connecting to TraceForge…</p>
      </main>
    );
  if (!user)
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand">
            <ShieldCheck />
            <span>TRACEFORGE</span>
          </div>
          <Badge tone="green">SECURITY FLIGHT RECORDER</Badge>
          <h1>
            Every event.
            <br />A clearer story.
          </h1>
          <p>Sign in to your local investigation workspace.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              await action(async () => {
                await api("/api/login", {
                  method: "POST",
                  body: JSON.stringify({
                    username: f.get("username"),
                    password: f.get("password"),
                  }),
                });
                setUser(await api("/api/me"));
              }, "Signed in");
            }}
          >
            <label>
              Username
              <input
                name="username"
                defaultValue="admin"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <Button disabled={busy}>Enter workspace</Button>
          </form>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <small>Use the credentials in your local .env file.</small>
        </div>
      </main>
    );
  const analyst = user.role !== "VIEWER";
  const cards = [
    [
      "Ingested events",
      overview?.events?.toLocaleString() ?? "—",
      "In selected window",
      Activity,
    ],
    [
      "Active services",
      overview?.services ?? "—",
      "Observed in telemetry",
      Network,
    ],
    [
      "Detection alerts",
      overview?.alerts ?? "—",
      "Indicators requiring review",
      TriangleAlert,
    ],
    [
      "Mean latency",
      overview?.latency_ms != null
        ? overview.latency_ms.toFixed(1) + " ms"
        : "—",
      "From recorded spans",
      Clock3,
    ],
  ] as const;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck />
          <span>TRACEFORGE</span>
        </div>
        <div className="workspace">
          <span className="workspace-icon">T</span>
          <div>
            Local workspace<small>Defensive operations</small>
          </div>
          <Badge>DEV</Badge>
        </div>
        <p className="nav-label">INVESTIGATION CONSOLE</p>
        <nav>
          {navigation.map(([name, Icon]) => (
            <button
              key={name}
              className={tab === name ? "active" : ""}
              onClick={() => setTab(name)}
            >
              <Icon size={18} />
              {name}
              {name === "Incidents" && incidents.length > 0 && (
                <span className="count">{incidents.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Shield size={20} />
          <p>
            Evidence before assumptions.
            <small>Local telemetry · No paid APIs</small>
          </p>
        </div>
        <button
          className="user"
          onClick={() =>
            void action(async () => {
              await api("/api/logout", { method: "POST" });
              setUser(null);
            }, "Signed out")
          }
        >
          <span className="avatar">{user.username[0].toUpperCase()}</span>
          <span>
            {user.username}
            <small>{user.role.replace("_", " ")}</small>
          </span>
          <LogOut size={17} />
        </button>
      </aside>
      <main className="main">
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span> Security operations
          </div>
          <div className="header-right">
            <Badge tone={live ? "green" : "amber"}>
              {live ? "● Live connection" : "Polling · reconnecting"}
            </Badge>
            <span className="divider" />
            <span className="date">
              {new Date().toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">TRACE. CORRELATE. RECONSTRUCT.</div>
              <h1>{tab === "Overview" ? "Security overview" : tab}</h1>
              <p>
                {tab === "Overview"
                  ? "A live picture of your systems, grounded in recorded evidence."
                  : "Follow the evidence. Keep uncertainty visible."}
              </p>
            </div>
            <div className="toolbar">
              <select
                aria-label="Time range"
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
              >
                <option value={15}>Last 15 minutes</option>
                <option value={60}>Last hour</option>
                <option value={1440}>Last 24 hours</option>
                <option value={43200}>Last 30 days</option>
              </select>
              <Button variant="outline" onClick={() => void refresh()}>
                Refresh
              </Button>
            </div>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {notice && (
            <div className="notice" role="status" onClick={() => setNotice("")}>
              {notice}
              <span>Dismiss</span>
            </div>
          )}
          {tab === "Overview" && (
            <>
              <div className="stats">
                {cards.map(([label, value, caption, Icon]) => (
                  <section className="stat" key={label}>
                    <div>
                      {label}
                      <Icon size={18} />
                    </div>
                    <strong>{value}</strong>
                    <small>{caption}</small>
                  </section>
                ))}
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <div className="panel-title">
                    <h2>Telemetry activity</h2>
                    <Badge tone="green">OBSERVED EVENTS</Badge>
                  </div>
                  <p className="subtle">Volume over the selected period</p>
                  <div className="chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={overview?.trend ?? []}>
                        <defs>
                          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#5be0bd"
                              stopOpacity={0.3}
                            />
                            <stop
                              offset="100%"
                              stopColor="#5be0bd"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#20313d" vertical={false} />
                        <XAxis
                          dataKey="time"
                          stroke="#7f97a6"
                          tickLine={false}
                        />
                        <YAxis stroke="#7f97a6" tickLine={false} width={35} />
                        <Tooltip
                          contentStyle={{
                            background: "#142532",
                            border: "1px solid #36505e",
                            borderRadius: 8,
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="events"
                          isAnimationActive={false}
                          dot={{ r: 3, fill: "#5be0bd" }}
                          stroke="#5be0bd"
                          fill="url(#fill)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </section>
                <section className="panel pipeline">
                  <div className="panel-title">
                    <h2>Pipeline health</h2>
                    <Activity size={18} />
                  </div>
                  {[
                    [
                      "Ingestion worker",
                      overview?.pipeline.ingestion_worker
                        ? "Running"
                        : "Unavailable",
                    ],
                    [
                      "Correlation worker",
                      overview?.pipeline.correlation_worker
                        ? "Running"
                        : "Unavailable",
                    ],
                    ["Buffered events", overview?.pipeline.queue ?? "Unknown"],
                    [
                      "Processing lag",
                      (overview?.lag_seconds ?? 0).toFixed(1) + " s",
                    ],
                    [
                      "Dead-letter events",
                      overview?.pipeline.dead_letters ?? "Unknown",
                    ],
                    ["Authentication failures", overview?.auth_failures ?? 0],
                    [
                      "HTTP error rate",
                      overview?.error_rate != null
                        ? (overview.error_rate * 100).toFixed(1) + "%"
                        : "Unknown",
                    ],
                  ].map(([k, v]) => (
                    <div className="metric-row" key={k}>
                      <span>{k}</span>
                      <strong>{v}</strong>
                    </div>
                  ))}
                  <p className="hint">
                    {overview?.truncated
                      ? "Showing a capped 10,000-event sample."
                      : "Metrics derive from stored telemetry."}
                  </p>
                </section>
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <div className="panel-title">
                    <h2>Observed service topology</h2>
                    <button
                      className="text-button"
                      onClick={() => setTab("Service graph")}
                    >
                      Explore graph
                    </button>
                  </div>
                  <ServiceGraph data={graph} onSelect={pickService} />
                  <p className="hint">
                    {graph.missing_parents} missing parent spans · Communication
                    does not prove attacker movement.
                  </p>
                </section>
                <section className="panel">
                  <div className="panel-title">
                    <h2>Recent detections</h2>
                    <Badge>{alerts.length}</Badge>
                  </div>
                  {alerts.slice(0, 5).map((a) => (
                    <div className="alert-card" key={a.id}>
                      <div>
                        <Badge tone={a.severity === "high" ? "red" : "amber"}>
                          {a.severity}
                        </Badge>
                        <small>{time(a.timestamp)}</small>
                      </div>
                      <h3>{a.detail.name}</h3>
                      <p>
                        {a.evidence.length} evidence records · {a.detail.origin}
                      </p>
                      <button
                        className="text-button"
                        onClick={() => {
                          const i = incidents.find((i) =>
                            i.detection_ids.includes(a.id),
                          );
                          if (i) void openIncident(i.id);
                        }}
                      >
                        Investigate
                      </button>
                    </div>
                  ))}
                  {!alerts.length && (
                    <Empty text="No detection alerts. Generate telemetry or run a controlled scenario." />
                  )}
                </section>
              </div>
              <section className="panel">
                <div className="panel-title">
                  <h2>Statistical baselines</h2>
                  <Badge>HELD-OUT OBSERVATION</Badge>
                </div>
                {overview?.anomalies.map((a) => (
                  <div className="metric-row" key={a.service}>
                    <strong>{a.service}</strong>
                    <span>{a.observed.toFixed(1)} ms observed</span>
                    <span>Baseline {a.baseline?.toFixed(1) ?? "—"} ms</span>
                    <Badge tone={a.anomalous ? "amber" : ""}>
                      Z {a.z_score?.toFixed(2) ?? "unavailable"}
                    </Badge>
                    <small>{a.reason}</small>
                  </div>
                ))}
                {!overview?.anomalies.length && (
                  <Empty text="Latency baseline unavailable until request telemetry arrives." />
                )}
              </section>
            </>
          )}
          {tab === "Event explorer" && (
            <section className="panel">
              <div className="filters">
                <div className="search">
                  <Search size={17} />
                  <input
                    placeholder="Search event, trace, or account ID"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select
                  aria-label="Service"
                  value={service}
                  onChange={(e) => setService(e.target.value)}
                >
                  <option value="">All services</option>
                  {graph.nodes.map((n) => (
                    <option key={n.id}>{n.id}</option>
                  ))}
                </select>
                <Badge>Latest 200 matching events</Badge>
              </div>
              <EventTable events={events} onSelect={setSelected} />
            </section>
          )}
          {tab === "Service graph" && (
            <section className="panel large-graph">
              <div className="panel-title">
                <h2>Observed dependencies</h2>
                <Badge>{graph.nodes.length} services</Badge>
              </div>
              <ServiceGraph data={graph} onSelect={pickService} />
              <p className="hint">
                {graph.limitations} Missing parents: {graph.missing_parents}.
              </p>
            </section>
          )}
          {tab === "Incidents" && (
            <>
              <div className="filters">
                <select
                  aria-label="Alert severity"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  <option value="">All alert severities</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                </select>
              </div>
              <section className="panel">
                <div className="panel-title">
                  <h2>Incident queue</h2>
                  <Badge>{incidents.length} incidents</Badge>
                </div>
                {incidents.map((i) => (
                  <button
                    className="incident-row"
                    key={i.id}
                    onClick={() => void openIncident(i.id)}
                  >
                    <div className="incident-icon">
                      <Layers3 size={20} />
                    </div>
                    <div>
                      <strong>{i.id}</strong>
                      <small>
                        {time(i.start)} – {time(i.end)} ·{" "}
                        {i.detection_ids.length} detections
                      </small>
                    </div>
                    <Badge>{i.status}</Badge>
                    <span>Open investigation</span>
                  </button>
                ))}
                {!incidents.length && (
                  <Empty text="No correlated incidents. Normal traffic does not automatically become an incident." />
                )}
              </section>
              <section className="panel">
                <h2>Alert management</h2>
                {alerts.map((a) => (
                  <div className="alert-management" key={a.id}>
                    <div>
                      <Badge tone={a.severity === "high" ? "red" : "amber"}>
                        {a.severity}
                      </Badge>
                      <h3>{a.detail.name}</h3>
                      <p>{a.detail.limitations}</p>
                      <small>
                        Observed {a.detail.observed} / threshold{" "}
                        {a.detail.threshold}
                      </small>
                    </div>
                    <input
                      aria-label={"Assignee " + a.id}
                      placeholder="Assign analyst"
                      defaultValue={a.state.assignee ?? ""}
                      disabled={!analyst}
                      onBlur={(e) => {
                        if (e.target.value !== (a.state.assignee ?? ""))
                          void action(
                            () =>
                              api("/api/alerts/" + a.id, {
                                method: "PATCH",
                                body: JSON.stringify({
                                  ...a.state,
                                  assignee: e.target.value,
                                }),
                              }),
                            "Assignment saved",
                          );
                      }}
                    />
                    <Button
                      disabled={!analyst || busy}
                      variant="outline"
                      onClick={() =>
                        void action(
                          () =>
                            api("/api/alerts/" + a.id, {
                              method: "PATCH",
                              body: JSON.stringify({
                                ...a.state,
                                acknowledged: true,
                              }),
                            }),
                          "Alert acknowledged",
                        )
                      }
                    >
                      {a.state.acknowledged ? "Acknowledged" : "Acknowledge"}
                    </Button>
                    <Button
                      disabled={!analyst || busy}
                      variant="outline"
                      onClick={() =>
                        void action(
                          () =>
                            api("/api/alerts/" + a.id, {
                              method: "PATCH",
                              body: JSON.stringify({
                                ...a.state,
                                escalated: true,
                              }),
                            }),
                          "Alert escalated",
                        )
                      }
                    >
                      Escalate
                    </Button>
                    <input
                      aria-label={"Resolution " + a.id}
                      placeholder="Resolution reason"
                      defaultValue={a.state.resolution ?? ""}
                      disabled={!analyst}
                      onBlur={(e) => {
                        if (e.target.value !== (a.state.resolution ?? ""))
                          void action(
                            () =>
                              api("/api/alerts/" + a.id, {
                                method: "PATCH",
                                body: JSON.stringify({
                                  ...a.state,
                                  resolution: e.target.value,
                                }),
                              }),
                            "Resolution saved",
                          );
                      }}
                    />
                  </div>
                ))}
              </section>
            </>
          )}
          {tab === "Time machine" &&
            (!detail ? (
              <section className="panel">
                <Empty text="Select an incident to reconstruct its recorded timeline." />
                {incidents.map((i) => (
                  <Button
                    key={i.id}
                    variant="outline"
                    onClick={() => void openIncident(i.id)}
                  >
                    {i.id}
                  </Button>
                ))}
              </section>
            ) : (
              <>
                <section className="panel replay">
                  <div className="panel-title">
                    <div>
                      <Badge tone="green">SECURITY TIME MACHINE</Badge>
                      <h2>{detail.id}</h2>
                    </div>
                    <div className="toolbar">
                      <Button
                        variant="outline"
                        onClick={() => void download("json")}
                      >
                        <Download size={15} />
                        JSON evidence
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => void download("pdf")}
                      >
                        <Download size={15} />
                        PDF report
                      </Button>
                    </div>
                  </div>
                  <p className="hint">{detail.limitations}</p>
                  <div className="replay-time">
                    {detail.events[cursor]
                      ? time(detail.events[cursor].timestamp)
                      : "No events"}
                    <span>
                      EVENT {cursor + 1} OF {detail.events.length}
                    </span>
                  </div>
                  <input
                    aria-label="Timeline position"
                    className="scrubber"
                    type="range"
                    min={0}
                    max={Math.max(0, detail.events.length - 1)}
                    value={cursor}
                    onChange={(e) => setCursor(Number(e.target.value))}
                  />
                  <div className="playback">
                    <Button
                      variant="outline"
                      aria-label="Previous event"
                      onClick={() => setCursor(Math.max(0, cursor - 1))}
                    >
                      <ArrowLeft size={17} />
                    </Button>
                    <Button onClick={() => setPlaying(!playing)}>
                      {playing ? <Pause size={17} /> : <Play size={17} />}{" "}
                      {playing ? "Pause replay" : "Play timeline"}
                    </Button>
                    <Button
                      variant="outline"
                      aria-label="Next event"
                      onClick={() =>
                        setCursor(
                          Math.min(detail.events.length - 1, cursor + 1),
                        )
                      }
                    >
                      <ArrowRight size={17} />
                    </Button>
                    <Badge>
                      {detail.events[cursor]?.origin ?? "unknown origin"}
                    </Badge>
                  </div>
                </section>
                <div className="overview-grid">
                  <section className="panel">
                    <h2>Recorded timeline</h2>
                    <div className="timeline">
                      {detail.events.map((e, i) => (
                        <button
                          key={e.id}
                          className={
                            "timeline-event " +
                            (i === cursor ? "chosen" : "") +
                            (i > cursor ? " future" : "")
                          }
                          onClick={() => {
                            setCursor(i);
                            setSelected(e);
                          }}
                        >
                          <span className="timeline-dot" />
                          <small>{time(e.timestamp)}</small>
                          <div>
                            <strong>{e.service}</strong>
                            <p>
                              {e.kind} ·{" "}
                              {String(
                                e.attributes.outcome ??
                                  e.attributes.path ??
                                  e.attributes.name ??
                                  e.attributes.status ??
                                  "Recorded event",
                              )}
                            </p>
                          </div>
                          <Badge>{e.origin}</Badge>
                        </button>
                      ))}
                    </div>
                  </section>
                  <section className="panel">
                    <h2>Historical service state</h2>
                    <ServiceGraph
                      data={historicalGraph(detail.events.slice(0, cursor + 1))}
                      onSelect={(id) => {
                        const e = detail.events
                          .slice(0, cursor + 1)
                          .find((e) => e.service === id);
                        if (e) setSelected(e);
                      }}
                    />
                    <p className="hint">
                      Only incident evidence recorded through the selected event
                      is shown.
                    </p>
                    <h3>Baseline comparison</h3>
                    <p className="subtle">
                      Previous five minutes:{" "}
                      {detail.baseline_graph.nodes.length} observed services;
                      incident: {detail.graph.nodes.length}. An empty baseline
                      is insufficient evidence.
                    </p>
                  </section>
                </div>
                <section className="panel">
                  <div className="panel-title">
                    <h2>Investigation workspace</h2>
                    <Button
                      variant="outline"
                      onClick={() =>
                        void action(async () => {
                          const v = await api<{
                            valid: boolean;
                            count: number;
                            errors: string[];
                          }>("/api/evidence/verify");
                          if (!v.valid)
                            throw new Error(
                              "INTEGRITY FAILURE: " + v.errors.join(", "),
                            );
                          setNotice(
                            "Evidence chain verified: " + v.count + " records",
                          );
                        }, "Evidence verification complete")
                      }
                    >
                      <ShieldCheck size={17} />
                      Verify evidence
                    </Button>
                  </div>
                  <form
                    className="status-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      void action(async () => {
                        await api("/api/incidents/" + detail.id, {
                          method: "PATCH",
                          body: JSON.stringify({
                            status: f.get("status"),
                            reason: f.get("reason"),
                          }),
                        });
                        setDetail(await api("/api/incidents/" + detail.id));
                      }, "Status change recorded");
                    }}
                  >
                    <select
                      name="status"
                      defaultValue={detail.status}
                      disabled={!analyst}
                    >
                      {[
                        "NEW",
                        "TRIAGED",
                        "INVESTIGATING",
                        "CONTAINED",
                        "RESOLVED",
                        "FALSE_POSITIVE",
                      ].map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                    <input
                      name="reason"
                      placeholder="Reason for status change"
                      required
                      disabled={!analyst}
                    />
                    <Button disabled={!analyst || busy}>Save status</Button>
                  </form>
                  <div className="hypothesis">
                    <TriangleAlert size={18} />
                    <div>
                      <strong>Evidence-based hypotheses</strong>
                      {detail.hypotheses.map((h) => (
                        <p key={h}>{h}</p>
                      ))}
                    </div>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action(async () => {
                        await api("/api/incidents/" + detail.id + "/notes", {
                          method: "POST",
                          body: JSON.stringify({
                            text: note,
                            bookmark:
                              selected &&
                              detail.events.some((e) => e.id === selected.id)
                                ? selected.id
                                : null,
                          }),
                        });
                        setNote("");
                        setDetail(await api("/api/incidents/" + detail.id));
                      }, "Investigation note saved");
                    }}
                  >
                    <textarea
                      placeholder="Record findings, uncertainty, or a hypothesis. The selected incident event will be bookmarked."
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      disabled={!analyst}
                      required
                    />
                    <Button disabled={!analyst || busy}>
                      Add note & bookmark
                    </Button>
                  </form>
                  {detail.notes.map((n) => (
                    <div className="note" key={n.id}>
                      <strong>{n.author}</strong>
                      <p>{n.text}</p>
                      {n.bookmark && <small>Bookmark: {n.bookmark}</small>}
                    </div>
                  ))}
                </section>
              </>
            ))}
          {tab === "Detection rules" && (
            <div className="rule-grid">
              {rules.map((r) => (
                <section className="panel" key={r.id}>
                  <div className="panel-title">
                    <h2>{r.name}</h2>
                    <Badge tone={r.enabled ? "green" : ""}>
                      {r.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </div>
                  <p>{r.limitations}</p>
                  <small>Required: {r.required.join(", ")}</small>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      void action(
                        () =>
                          api("/api/rules/" + r.id, {
                            method: "PATCH",
                            body: JSON.stringify({
                              enabled: f.get("enabled") === "on",
                              threshold: Number(f.get("threshold")),
                              window_seconds: Number(f.get("window")),
                              suppressed_services: String(f.get("suppress"))
                                .split(",")
                                .map((x) => x.trim())
                                .filter(Boolean),
                            }),
                          }),
                        "Rule configuration saved",
                      );
                    }}
                  >
                    <div className="rule-inputs">
                      <label>
                        Threshold
                        <input
                          type="number"
                          name="threshold"
                          step="any"
                          min="0.01"
                          defaultValue={r.threshold}
                          disabled={user.role !== "ADMIN"}
                        />
                      </label>
                      <label>
                        Window (seconds)
                        <input
                          type="number"
                          name="window"
                          min="1"
                          max="3600"
                          defaultValue={r.window_seconds}
                          disabled={user.role !== "ADMIN"}
                        />
                      </label>
                    </div>
                    <label>
                      Suppressed services
                      <input
                        name="suppress"
                        defaultValue={r.suppressed_services.join(",")}
                        placeholder="Comma-separated service names"
                        disabled={user.role !== "ADMIN"}
                      />
                    </label>
                    <div className="rule-footer">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          name="enabled"
                          defaultChecked={r.enabled}
                          disabled={user.role !== "ADMIN"}
                        />
                        Enabled
                      </label>
                      <Button
                        variant="outline"
                        disabled={user.role !== "ADMIN" || busy}
                      >
                        Save rule
                      </Button>
                    </div>
                  </form>
                </section>
              ))}
            </div>
          )}
          {tab === "Scenario lab" && (
            <>
              <div className="callout">
                <FlaskConical />
                <p>
                  Scenarios create explicitly synthetic records in the local
                  pipeline. No external systems are contacted. Expected
                  detections are ground truth for testing, not fabricated
                  alerts.
                </p>
              </div>
              <div className="rule-grid">
                {Object.entries(scenarios).map(([code, s]) => (
                  <section className="panel scenario" key={code}>
                    <Badge>SYNTHETIC · {code}</Badge>
                    <h2>{s.name}</h2>
                    <p>{s.truth}</p>
                    <div className="scenario-expect">
                      <small>EXPECTED DETECTIONS</small>
                      <p>{s.expected.join(", ") || "None — benign activity"}</p>
                    </div>
                    <p className="hint">
                      False-positive considerations: {s.false_positives}
                    </p>
                    <Button
                      disabled={!analyst || busy}
                      onClick={() =>
                        void action(
                          () =>
                            api("/api/scenarios/" + code, { method: "POST" }),
                          "Scenario queued. Detections appear after processing.",
                        )
                      }
                    >
                      <Play size={16} />
                      Run scenario {code}
                    </Button>
                  </section>
                ))}
              </div>
            </>
          )}
          {tab === "Audit trail" && (
            <section className="panel">
              <h2>Custody & analyst actions</h2>
              {user.role === "VIEWER" ? (
                <Empty text="Audit history requires an analyst role." />
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((a, i) => (
                      <tr key={i}>
                        <td>{time(a.timestamp)}</td>
                        <td>{a.actor}</td>
                        <td>{a.action}</td>
                        <td className="mono">{a.target}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}
          <footer>
            <span>
              <ShieldCheck size={14} /> TraceForge · Evidence-led security
            </span>
            <span>All times shown in your local timezone</span>
          </footer>
        </div>
      </main>
      {selected && (
        <div className="drawer" role="dialog" aria-label="Event details">
          <div className="panel-title">
            <h2>Event details</h2>
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Close
            </Button>
          </div>
          <Badge tone={selected.origin === "synthetic" ? "amber" : "green"}>
            {selected.origin}
          </Badge>
          <h3>
            {selected.service} / {selected.kind}
          </h3>
          <p>{new Date(selected.timestamp).toLocaleString()}</p>
          <p className="hint">
            {selected.trace_id
              ? "Trace correlation available"
              : "Evidence gap: no trace identifier"}
            {selected.parent_span_id ? " · Parent span recorded" : ""}
          </p>
          <pre>{JSON.stringify(selected, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
function Empty({ text }: { text: string }) {
  return (
    <div className="empty">
      <CheckCircle2 size={25} />
      <p>{text}</p>
    </div>
  );
}
function EventTable({
  events,
  onSelect,
}: {
  events: Event[];
  onSelect: (e: Event) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Service</th>
            <th>Event</th>
            <th>Trace / correlation</th>
            <th>Provenance</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr
              key={e.id}
              onClick={() => onSelect(e)}
              tabIndex={0}
              onKeyDown={(k) => {
                if (k.key === "Enter") onSelect(e);
              }}
            >
              <td className="mono">{time(e.timestamp)}</td>
              <td>
                <strong>{e.service}</strong>
              </td>
              <td>
                {e.kind}
                <small>
                  {String(e.attributes.outcome ?? e.attributes.status ?? "")}
                </small>
              </td>
              <td className="mono">
                {e.trace_id?.slice(0, 16) ?? "Unknown correlation"}
              </td>
              <td>
                <Badge tone={e.origin === "synthetic" ? "amber" : "green"}>
                  {e.origin}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!events.length && (
        <Empty text="No matching events in this time window." />
      )}
    </div>
  );
}
function historicalGraph(events: Event[]): GraphData {
  const services = [...new Set(events.map((e) => e.service))];
  const edges: GraphData["edges"] = [];
  for (const e of events) {
    const parent = events.find(
      (p) =>
        p.trace_id &&
        p.trace_id === e.trace_id &&
        p.span_id === e.parent_span_id,
    );
    if (parent && parent.service !== e.service) {
      const edge = edges.find(
        (x) => x.source === parent.service && x.target === e.service,
      );
      if (edge) edge.count++;
      else
        edges.push({
          source: parent.service,
          target: e.service,
          count: 1,
          relationship: "observed",
        });
    }
  }
  return {
    nodes: services.map((id) => {
      const rows = events.filter((e) => e.service === id);
      const lat = rows
        .map((e) => e.attributes.latency_ms)
        .filter((v): v is number => typeof v === "number");
      return {
        id,
        events: rows.length,
        error_rate:
          rows.filter((e) => Number(e.attributes.status) >= 500).length /
          rows.length,
        latency_ms: lat.length
          ? lat.reduce((a, b) => a + b, 0) / lat.length
          : null,
      };
    }),
    edges,
    missing_parents: 0,
    limitations: "Partial observed state",
  };
}
