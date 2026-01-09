import { useEffect, useMemo, useState } from "react";

const apiUrl = import.meta.env.VITE_API_URL ?? "/api";

type Title = {
  id: number;
  type: "movie" | "series";
  name: string;
  original_name?: string | null;
  description?: string | null;
  year?: number | null;
  poster_url?: string | null;
  is_published: boolean;
};

type Season = {
  id: number;
  season_number: number;
  name?: string | null;
  episodes: Episode[];
};

type Episode = {
  id: number;
  episode_number: number;
  name: string;
  description?: string | null;
  air_date?: string | null;
  published_at?: string | null;
};

type Variant = {
  id: number;
  title_id: number;
  episode_id?: number | null;
  audio_id: number;
  quality_id: number;
  status: string;
  telegram_file_id?: string | null;
  error?: string | null;
  expected_filename: string;
};

type AudioTrack = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
};

type Quality = {
  id: number;
  name: string;
  height: number;
  is_active: boolean;
};

type UploadJob = {
  id: number;
  variant_id: number;
  status: string;
  attempts: number;
  local_path: string;
  last_error?: string | null;
};

const tabs = [
  { id: "dashboard", label: "Dashboard" },
  { id: "titles", label: "Titles" },
  { id: "variants", label: "Variants" },
  { id: "jobs", label: "Upload Jobs" },
  { id: "audio", label: "Audio Tracks" },
  { id: "qualities", label: "Qualities" },
];

async function apiFetch<T>(
  path: string,
  options: RequestInit,
  adminToken: string,
  adminUserId: string,
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers ?? {}),
  };
  if (adminToken) {
    headers["X-Admin-Token"] = adminToken;
  }
  if (adminUserId) {
    headers["X-Admin-User-Id"] = adminUserId;
  }
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return {} as T;
  }
  return response.json() as Promise<T>;
}

function formatDateInput(value?: string | null) {
  if (!value) return "";
  return value.slice(0, 10);
}

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [adminToken, setAdminToken] = useState(
    localStorage.getItem("kina_admin_token") ?? "",
  );
  const [adminUserId, setAdminUserId] = useState(
    localStorage.getItem("kina_admin_user_id") ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("kina_admin_token", adminToken);
  }, [adminToken]);

  useEffect(() => {
    localStorage.setItem("kina_admin_user_id", adminUserId);
  }, [adminUserId]);

  const api = useMemo(
    () => ({
      get: <T,>(path: string) =>
        apiFetch<T>(path, { method: "GET" }, adminToken, adminUserId),
      post: <T,>(path: string, body?: unknown) =>
        apiFetch<T>(
          path,
          { method: "POST", body: body ? JSON.stringify(body) : undefined },
          adminToken,
          adminUserId,
        ),
      patch: <T,>(path: string, body: unknown) =>
        apiFetch<T>(
          path,
          { method: "PATCH", body: JSON.stringify(body) },
          adminToken,
          adminUserId,
        ),
    }),
    [adminToken, adminUserId],
  );

  return (
    <div style={{ fontFamily: "Inter, system-ui, sans-serif", color: "#111827" }}>
      <header
        style={{
          padding: "1.5rem 2rem",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Kina Admin</h1>
          <p style={{ margin: "0.25rem 0 0", color: "#6b7280" }}>
            API: {apiUrl}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <input
            placeholder="ADMIN_SERVICE_TOKEN"
            value={adminToken}
            onChange={(event) => setAdminToken(event.target.value)}
            style={{ padding: "0.5rem", width: "220px" }}
          />
          <input
            placeholder="TG user id (allowlist)"
            value={adminUserId}
            onChange={(event) => setAdminUserId(event.target.value)}
            style={{ padding: "0.5rem", width: "180px" }}
          />
        </div>
      </header>

      <div style={{ display: "flex", minHeight: "calc(100vh - 88px)" }}>
        <nav
          style={{
            width: "220px",
            borderRight: "1px solid #e5e7eb",
            padding: "1.5rem 1rem",
            background: "#f9fafb",
          }}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: "block",
                width: "100%",
                padding: "0.6rem 0.75rem",
                marginBottom: "0.5rem",
                textAlign: "left",
                border: "1px solid transparent",
                borderRadius: "8px",
                background: activeTab === tab.id ? "#111827" : "transparent",
                color: activeTab === tab.id ? "#fff" : "#111827",
                cursor: "pointer",
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <main style={{ flex: 1, padding: "1.5rem 2rem" }}>
          {error && (
            <div
              style={{
                background: "#fee2e2",
                color: "#991b1b",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                marginBottom: "1rem",
              }}
            >
              {error}
            </div>
          )}

          {activeTab === "dashboard" && <Dashboard api={api} onError={setError} />}
          {activeTab === "titles" && <TitlesView api={api} onError={setError} />}
          {activeTab === "variants" && (
            <VariantsView api={api} onError={setError} />
          )}
          {activeTab === "jobs" && <JobsView api={api} onError={setError} />}
          {activeTab === "audio" && <AudioView api={api} onError={setError} />}
          {activeTab === "qualities" && (
            <QualityView api={api} onError={setError} />
          )}
        </main>
      </div>
    </div>
  );
}

function Dashboard({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [stats, setStats] = useState({
    titles: 0,
    pendingVariants: 0,
    readyVariants: 0,
    queuedJobs: 0,
    failedJobs: 0,
  });

  useEffect(() => {
    const load = async () => {
      try {
        const [titles, pending, ready, queued, failed] = await Promise.all([
          api.get<{ total: number }>("/admin/titles?limit=1"),
          api.get<{ total: number }>("/admin/variants?status=pending&limit=1"),
          api.get<{ total: number }>("/admin/variants?status=ready&limit=1"),
          api.get<{ total: number }>("/admin/upload_jobs?status=queued&limit=1"),
          api.get<{ total: number }>("/admin/upload_jobs?status=failed&limit=1"),
        ]);
        setStats({
          titles: titles.total,
          pendingVariants: pending.total,
          readyVariants: ready.total,
          queuedJobs: queued.total,
          failedJobs: failed.total,
        });
      } catch (err) {
        onError((err as Error).message);
      }
    };
    load();
  }, [api, onError]);

  return (
    <section>
      <h2>Dashboard</h2>
      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(3, 1fr)" }}>
        <StatCard label="Titles" value={stats.titles} />
        <StatCard label="Variants pending" value={stats.pendingVariants} />
        <StatCard label="Variants ready" value={stats.readyVariants} />
        <StatCard label="Jobs queued" value={stats.queuedJobs} />
        <StatCard label="Jobs failed" value={stats.failedJobs} />
      </div>
    </section>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "12px",
        padding: "1rem",
        background: "#fff",
      }}
    >
      <div style={{ fontSize: "0.85rem", color: "#6b7280" }}>{label}</div>
      <div style={{ fontSize: "1.5rem", fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function TitlesView({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [titles, setTitles] = useState<Title[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [newTitle, setNewTitle] = useState({
    type: "movie",
    name: "",
    year: "",
  });

  const loadTitles = async () => {
    try {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (typeFilter) params.set("type", typeFilter);
      const data = await api.get<{ items: Title[]; total: number }>(
        `/admin/titles?${params.toString()}`,
      );
      setTitles(data.items);
      setTotal(data.total);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    loadTitles();
  }, [typeFilter]);

  const handleCreate = async () => {
    try {
      const payload = {
        type: newTitle.type,
        name: newTitle.name,
        year: newTitle.year ? Number(newTitle.year) : null,
      };
      const result = await api.post<{ id: number }>("/admin/titles", payload);
      setSelectedId(result.id);
      setNewTitle({ type: "movie", name: "", year: "" });
      loadTitles();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  return (
    <section>
      <h2>Titles</h2>
      <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
        <input
          placeholder="Search by name"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ padding: "0.5rem", flex: 1 }}
        />
        <select
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
          style={{ padding: "0.5rem" }}
        >
          <option value="">All types</option>
          <option value="movie">Movie</option>
          <option value="series">Series</option>
        </select>
        <button
          type="button"
          onClick={loadTitles}
          style={{ padding: "0.5rem 1rem" }}
        >
          Search
        </button>
      </div>

      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "1fr 2fr" }}>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>Create title</h3>
          <label style={{ display: "block", marginBottom: "0.5rem" }}>
            Type
            <select
              value={newTitle.type}
              onChange={(event) =>
                setNewTitle((prev) => ({ ...prev, type: event.target.value }))
              }
              style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
            >
              <option value="movie">Movie</option>
              <option value="series">Series</option>
            </select>
          </label>
          <label style={{ display: "block", marginBottom: "0.5rem" }}>
            Name
            <input
              value={newTitle.name}
              onChange={(event) =>
                setNewTitle((prev) => ({ ...prev, name: event.target.value }))
              }
              style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
            />
          </label>
          <label style={{ display: "block", marginBottom: "0.5rem" }}>
            Year
            <input
              value={newTitle.year}
              onChange={(event) =>
                setNewTitle((prev) => ({ ...prev, year: event.target.value }))
              }
              style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
            />
          </label>
          <button type="button" onClick={handleCreate} style={{ padding: "0.5rem 1rem" }}>
            Create
          </button>
        </div>

        <div>
          <div style={{ marginBottom: "0.5rem", color: "#6b7280" }}>
            Total: {total}
          </div>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px" }}>
            {titles.map((title) => (
              <button
                key={title.id}
                type="button"
                onClick={() => setSelectedId(title.id)}
                style={{
                  width: "100%",
                  padding: "0.75rem 1rem",
                  textAlign: "left",
                  border: "none",
                  borderBottom: "1px solid #e5e7eb",
                  background: selectedId === title.id ? "#eef2ff" : "transparent",
                  cursor: "pointer",
                }}
              >
                <strong>{title.name}</strong>
                <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                  {title.type} · {title.year ?? "n/a"}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {selectedId && (
        <TitleEditor key={selectedId} titleId={selectedId} api={api} onError={onError} />
      )}
    </section>
  );
}

function TitleEditor({
  titleId,
  api,
  onError,
}: {
  titleId: number;
  api: any;
  onError: (msg: string) => void;
}) {
  const [title, setTitle] = useState<Title | null>(null);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [tab, setTab] = useState("details");
  const [newSeason, setNewSeason] = useState({ season_number: "", name: "" });
  const [newEpisode, setNewEpisode] = useState({
    season_id: "",
    episode_number: "",
    name: "",
    air_date: "",
  });
  const [editEpisode, setEditEpisode] = useState<Episode | null>(null);
  const [audioTracks, setAudioTracks] = useState<AudioTrack[]>([]);
  const [qualities, setQualities] = useState<Quality[]>([]);

  const loadTitle = async () => {
    try {
      const data = await api.get<{ seasons: Season[] } & Title>(`/admin/titles/${titleId}`);
      setTitle(data);
      setSeasons(data.seasons || []);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const loadMeta = async () => {
    try {
      const [audio, quality] = await Promise.all([
        api.get<{ items: AudioTrack[] }>("/admin/audio_tracks"),
        api.get<{ items: Quality[] }>("/admin/qualities"),
      ]);
      setAudioTracks(audio.items);
      setQualities(quality.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    loadTitle();
    loadMeta();
  }, [titleId]);

  const handleTitleSave = async () => {
    if (!title) return;
    try {
      await api.patch(`/admin/titles/${titleId}`, {
        name: title.name,
        original_name: title.original_name,
        description: title.description,
        year: title.year,
        poster_url: title.poster_url,
        is_published: title.is_published,
      });
      loadTitle();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleSeasonCreate = async () => {
    try {
      await api.post(`/admin/titles/${titleId}/seasons`, {
        season_number: Number(newSeason.season_number),
        name: newSeason.name || null,
      });
      setNewSeason({ season_number: "", name: "" });
      loadTitle();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleEpisodeCreate = async () => {
    if (!newEpisode.season_id) return;
    try {
      await api.post(`/admin/seasons/${newEpisode.season_id}/episodes`, {
        episode_number: Number(newEpisode.episode_number),
        name: newEpisode.name,
        air_date: newEpisode.air_date || null,
      });
      setNewEpisode({ season_id: "", episode_number: "", name: "", air_date: "" });
      loadTitle();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleEpisodeSave = async () => {
    if (!editEpisode) return;
    try {
      await api.patch(`/admin/episodes/${editEpisode.id}`, {
        name: editEpisode.name,
        description: editEpisode.description,
        air_date: editEpisode.air_date || null,
      });
      setEditEpisode(null);
      loadTitle();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleEpisodePublish = async (episodeId: number) => {
    try {
      await api.post(`/admin/episodes/${episodeId}/publish`);
      loadTitle();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  if (!title) return null;

  return (
    <div style={{ marginTop: "2rem" }}>
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
        <button
          type="button"
          onClick={() => setTab("details")}
          style={{
            padding: "0.5rem 1rem",
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            background: tab === "details" ? "#111827" : "transparent",
            color: tab === "details" ? "#fff" : "#111827",
          }}
        >
          Details
        </button>
        <button
          type="button"
          onClick={() => setTab("variants")}
          style={{
            padding: "0.5rem 1rem",
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            background: tab === "variants" ? "#111827" : "transparent",
            color: tab === "variants" ? "#fff" : "#111827",
          }}
        >
          Variants
        </button>
      </div>

      {tab === "details" && (
        <div style={{ display: "grid", gap: "1.5rem" }}>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
            <h3>Title editor</h3>
            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              Name
              <input
                value={title.name}
                onChange={(event) =>
                  setTitle((prev) => (prev ? { ...prev, name: event.target.value } : prev))
                }
                style={{ display: "block", width: "100%" }}
              />
            </label>
            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              Original name
              <input
                value={title.original_name ?? ""}
                onChange={(event) =>
                  setTitle((prev) =>
                    prev ? { ...prev, original_name: event.target.value } : prev,
                  )
                }
                style={{ display: "block", width: "100%" }}
              />
            </label>
            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              Description
              <textarea
                value={title.description ?? ""}
                onChange={(event) =>
                  setTitle((prev) =>
                    prev ? { ...prev, description: event.target.value } : prev,
                  )
                }
                rows={3}
                style={{ display: "block", width: "100%" }}
              />
            </label>
            <div style={{ display: "flex", gap: "1rem" }}>
              <label style={{ flex: 1 }}>
                Year
                <input
                  value={title.year ?? ""}
                  onChange={(event) =>
                    setTitle((prev) =>
                      prev ? { ...prev, year: Number(event.target.value) || null } : prev,
                    )
                  }
                  style={{ display: "block", width: "100%" }}
                />
              </label>
              <label style={{ flex: 1 }}>
                Poster URL
                <input
                  value={title.poster_url ?? ""}
                  onChange={(event) =>
                    setTitle((prev) =>
                      prev ? { ...prev, poster_url: event.target.value } : prev,
                    )
                  }
                  style={{ display: "block", width: "100%" }}
                />
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="checkbox"
                  checked={title.is_published}
                  onChange={(event) =>
                    setTitle((prev) =>
                      prev ? { ...prev, is_published: event.target.checked } : prev,
                    )
                  }
                />
                Published
              </label>
            </div>
            <button type="button" onClick={handleTitleSave} style={{ marginTop: "0.75rem" }}>
              Save
            </button>
          </div>

          {title.type === "series" && (
            <div style={{ display: "grid", gap: "1rem" }}>
              <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
                <h3>Create season</h3>
                <input
                  placeholder="Season number"
                  value={newSeason.season_number}
                  onChange={(event) =>
                    setNewSeason((prev) => ({ ...prev, season_number: event.target.value }))
                  }
                  style={{ marginRight: "0.5rem" }}
                />
                <input
                  placeholder="Name"
                  value={newSeason.name}
                  onChange={(event) =>
                    setNewSeason((prev) => ({ ...prev, name: event.target.value }))
                  }
                  style={{ marginRight: "0.5rem" }}
                />
                <button type="button" onClick={handleSeasonCreate}>
                  Create season
                </button>
              </div>

              <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
                <h3>Create episode</h3>
                <select
                  value={newEpisode.season_id}
                  onChange={(event) =>
                    setNewEpisode((prev) => ({ ...prev, season_id: event.target.value }))
                  }
                  style={{ marginRight: "0.5rem" }}
                >
                  <option value="">Season</option>
                  {seasons.map((season) => (
                    <option key={season.id} value={season.id}>
                      Season {season.season_number}
                    </option>
                  ))}
                </select>
                <input
                  placeholder="Episode #"
                  value={newEpisode.episode_number}
                  onChange={(event) =>
                    setNewEpisode((prev) => ({
                      ...prev,
                      episode_number: event.target.value,
                    }))
                  }
                  style={{ marginRight: "0.5rem", width: "90px" }}
                />
                <input
                  placeholder="Episode name"
                  value={newEpisode.name}
                  onChange={(event) =>
                    setNewEpisode((prev) => ({ ...prev, name: event.target.value }))
                  }
                  style={{ marginRight: "0.5rem" }}
                />
                <input
                  type="date"
                  value={newEpisode.air_date}
                  onChange={(event) =>
                    setNewEpisode((prev) => ({ ...prev, air_date: event.target.value }))
                  }
                  style={{ marginRight: "0.5rem" }}
                />
                <button type="button" onClick={handleEpisodeCreate}>
                  Create episode
                </button>
              </div>

              {editEpisode && (
                <div
                  style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}
                >
                  <h3>Edit episode</h3>
                  <input
                    value={editEpisode.name}
                    onChange={(event) =>
                      setEditEpisode((prev) =>
                        prev ? { ...prev, name: event.target.value } : prev,
                      )
                    }
                    style={{ marginRight: "0.5rem" }}
                  />
                  <input
                    type="date"
                    value={formatDateInput(editEpisode.air_date)}
                    onChange={(event) =>
                      setEditEpisode((prev) =>
                        prev ? { ...prev, air_date: event.target.value } : prev,
                      )
                    }
                    style={{ marginRight: "0.5rem" }}
                  />
                  <input
                    placeholder="Description"
                    value={editEpisode.description ?? ""}
                    onChange={(event) =>
                      setEditEpisode((prev) =>
                        prev ? { ...prev, description: event.target.value } : prev,
                      )
                    }
                    style={{ marginRight: "0.5rem", width: "240px" }}
                  />
                  <button type="button" onClick={handleEpisodeSave}>
                    Save episode
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditEpisode(null)}
                    style={{ marginLeft: "0.5rem" }}
                  >
                    Cancel
                  </button>
                </div>
              )}

              <div style={{ display: "grid", gap: "1rem" }}>
                {seasons.map((season) => (
                  <div
                    key={season.id}
                    style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}
                  >
                    <h4>
                      Season {season.season_number} {season.name ? `· ${season.name}` : ""}
                    </h4>
                    {season.episodes.length === 0 && (
                      <p style={{ color: "#6b7280" }}>No episodes yet.</p>
                    )}
                    {season.episodes.map((episode) => (
                      <div
                        key={episode.id}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: "1rem",
                          padding: "0.5rem 0",
                          borderBottom: "1px solid #f3f4f6",
                        }}
                      >
                        <div>
                          <strong>
                            E{episode.episode_number}: {episode.name}
                          </strong>
                          <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                            Air: {episode.air_date ?? "n/a"} · Published:{" "}
                            {episode.published_at ? "yes" : "no"}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button type="button" onClick={() => setEditEpisode(episode)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleEpisodePublish(episode.id)}
                          >
                            Publish
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "variants" && (
        <TitleVariants
          titleId={titleId}
          api={api}
          onError={onError}
          audioTracks={audioTracks}
          qualities={qualities}
          seasons={seasons}
        />
      )}
    </div>
  );
}

function TitleVariants({
  titleId,
  api,
  onError,
  audioTracks,
  qualities,
  seasons,
}: {
  titleId: number;
  api: any;
  onError: (msg: string) => void;
  audioTracks: AudioTrack[];
  qualities: Quality[];
  seasons: Season[];
}) {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [newVariant, setNewVariant] = useState({
    episode_id: "",
    audio_id: "",
    quality_id: "",
    status: "pending",
  });

  const episodes = seasons.flatMap((season) => season.episodes);

  const loadVariants = async () => {
    try {
      const data = await api.get<{ items: Variant[] }>(
        `/admin/variants?title_id=${titleId}`,
      );
      setVariants(data.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    loadVariants();
  }, [titleId]);

  const handleCreate = async () => {
    try {
      await api.post("/admin/variants", {
        title_id: titleId,
        episode_id: newVariant.episode_id ? Number(newVariant.episode_id) : null,
        audio_id: Number(newVariant.audio_id),
        quality_id: Number(newVariant.quality_id),
        status: newVariant.status,
      });
      setNewVariant({ episode_id: "", audio_id: "", quality_id: "", status: "pending" });
      loadVariants();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const audioMap = new Map(audioTracks.map((track) => [track.id, track]));
  const qualityMap = new Map(qualities.map((quality) => [quality.id, quality]));

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        <h3>Create variant</h3>
        <select
          value={newVariant.episode_id}
          onChange={(event) =>
            setNewVariant((prev) => ({ ...prev, episode_id: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        >
          <option value="">Movie variant</option>
          {episodes.map((episode) => (
            <option key={episode.id} value={episode.id}>
              Episode {episode.episode_number}: {episode.name}
            </option>
          ))}
        </select>
        <select
          value={newVariant.audio_id}
          onChange={(event) =>
            setNewVariant((prev) => ({ ...prev, audio_id: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        >
          <option value="">Audio</option>
          {audioTracks.map((track) => (
            <option key={track.id} value={track.id}>
              {track.name} ({track.code})
            </option>
          ))}
        </select>
        <select
          value={newVariant.quality_id}
          onChange={(event) =>
            setNewVariant((prev) => ({ ...prev, quality_id: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        >
          <option value="">Quality</option>
          {qualities.map((quality) => (
            <option key={quality.id} value={quality.id}>
              {quality.name} ({quality.height}p)
            </option>
          ))}
        </select>
        <select
          value={newVariant.status}
          onChange={(event) =>
            setNewVariant((prev) => ({ ...prev, status: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        >
          <option value="pending">pending</option>
          <option value="ready">ready</option>
          <option value="failed">failed</option>
          <option value="uploading">uploading</option>
        </select>
        <button type="button" onClick={handleCreate}>
          Create variant
        </button>
      </div>

      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        <h3>Variants</h3>
        {variants.length === 0 && <p style={{ color: "#6b7280" }}>No variants yet.</p>}
        {variants.map((variant) => {
          const audio = audioMap.get(variant.audio_id);
          const quality = qualityMap.get(variant.quality_id);
          return (
            <div
              key={variant.id}
              style={{
                padding: "0.75rem 0",
                borderBottom: "1px solid #f3f4f6",
                display: "grid",
                gap: "0.35rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>
                  {variant.episode_id ? `Episode ${variant.episode_id}` : "Movie"} ·{" "}
                  {audio ? `${audio.name} (${audio.code})` : `Audio ${variant.audio_id}`} ·{" "}
                  {quality ? `${quality.name} (${quality.height}p)` : `Q ${variant.quality_id}`}
                </strong>
                <span>{variant.status}</span>
              </div>
              <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                Telegram file: {variant.telegram_file_id ?? "not uploaded"}
              </div>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <code style={{ background: "#f3f4f6", padding: "0.2rem 0.4rem" }}>
                  {variant.expected_filename}
                </code>
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(variant.expected_filename)}
                >
                  Copy
                </button>
              </div>
              <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                Загрузите файл на сервер в ingest с именем:{" "}
                <strong>{variant.expected_filename}</strong>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VariantsView({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [filters, setFilters] = useState({ title_id: "", episode_id: "", status: "" });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.title_id) params.set("title_id", filters.title_id);
      if (filters.episode_id) params.set("episode_id", filters.episode_id);
      if (filters.status) params.set("status", filters.status);
      const data = await api.get<{ items: Variant[] }>(
        `/admin/variants?${params.toString()}`,
      );
      setVariants(data.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <section>
      <h2>Variants</h2>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <input
          placeholder="Title ID"
          value={filters.title_id}
          onChange={(event) =>
            setFilters((prev) => ({ ...prev, title_id: event.target.value }))
          }
        />
        <input
          placeholder="Episode ID"
          value={filters.episode_id}
          onChange={(event) =>
            setFilters((prev) => ({ ...prev, episode_id: event.target.value }))
          }
        />
        <input
          placeholder="Status"
          value={filters.status}
          onChange={(event) =>
            setFilters((prev) => ({ ...prev, status: event.target.value }))
          }
        />
        <button type="button" onClick={load}>
          Apply
        </button>
      </div>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        {variants.map((variant) => (
          <div
            key={variant.id}
            style={{
              padding: "0.75rem 0",
              borderBottom: "1px solid #f3f4f6",
              display: "grid",
              gap: "0.35rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>
                Variant #{variant.id} · {variant.episode_id ? "Episode" : "Movie"}{" "}
                {variant.episode_id ?? variant.title_id}
              </strong>
              <span>{variant.status}</span>
            </div>
            <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
              Telegram file: {variant.telegram_file_id ?? "not uploaded"}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <code style={{ background: "#f3f4f6", padding: "0.2rem 0.4rem" }}>
                {variant.expected_filename}
              </code>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(variant.expected_filename)}
              >
                Copy
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function JobsView({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [statusFilter, setStatusFilter] = useState("");

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      const data = await api.get<{ items: UploadJob[] }>(
        `/admin/upload_jobs?${params.toString()}`,
      );
      setJobs(data.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleRetry = async (jobId: number) => {
    try {
      await api.post(`/admin/upload_jobs/${jobId}/retry`);
      load();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleRescan = async () => {
    try {
      await api.post("/admin/upload_jobs/rescan");
    } catch (err) {
      onError((err as Error).message);
    }
  };

  return (
    <section>
      <h2>Upload Jobs</h2>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <input
          placeholder="Status"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        />
        <button type="button" onClick={load}>
          Filter
        </button>
        <button type="button" onClick={handleRescan}>
          Rescan ingest
        </button>
      </div>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        {jobs.map((job) => (
          <div
            key={job.id}
            style={{
              padding: "0.75rem 0",
              borderBottom: "1px solid #f3f4f6",
              display: "grid",
              gap: "0.35rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>
                Job #{job.id} · Variant {job.variant_id}
              </strong>
              <span>{job.status}</span>
            </div>
            <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
              Attempts: {job.attempts} · Path: {job.local_path}
            </div>
            {job.last_error && (
              <div style={{ color: "#b91c1c", fontSize: "0.85rem" }}>
                Last error: {job.last_error}
              </div>
            )}
            <button type="button" onClick={() => handleRetry(job.id)}>
              Retry
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function AudioView({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [tracks, setTracks] = useState<AudioTrack[]>([]);
  const [newTrack, setNewTrack] = useState({ name: "", code: "" });
  const [editTrack, setEditTrack] = useState<AudioTrack | null>(null);

  const load = async () => {
    try {
      const data = await api.get<{ items: AudioTrack[] }>("/admin/audio_tracks");
      setTracks(data.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    try {
      await api.post("/admin/audio_tracks", {
        name: newTrack.name,
        code: newTrack.code,
        is_active: true,
      });
      setNewTrack({ name: "", code: "" });
      load();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleSave = async () => {
    if (!editTrack) return;
    try {
      await api.patch(`/admin/audio_tracks/${editTrack.id}`, {
        name: editTrack.name,
        code: editTrack.code,
        is_active: editTrack.is_active,
      });
      setEditTrack(null);
      load();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  return (
    <section>
      <h2>Audio Tracks</h2>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        <h3>Create track</h3>
        <input
          placeholder="Name"
          value={newTrack.name}
          onChange={(event) => setNewTrack((prev) => ({ ...prev, name: event.target.value }))}
          style={{ marginRight: "0.5rem" }}
        />
        <input
          placeholder="Code"
          value={newTrack.code}
          onChange={(event) => setNewTrack((prev) => ({ ...prev, code: event.target.value }))}
          style={{ marginRight: "0.5rem" }}
        />
        <button type="button" onClick={handleCreate}>
          Create
        </button>
      </div>
      {editTrack && (
        <div
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "1rem",
            marginTop: "1rem",
          }}
        >
          <h3>Edit track</h3>
          <input
            value={editTrack.name}
            onChange={(event) =>
              setEditTrack((prev) => (prev ? { ...prev, name: event.target.value } : prev))
            }
            style={{ marginRight: "0.5rem" }}
          />
          <input
            value={editTrack.code}
            onChange={(event) =>
              setEditTrack((prev) => (prev ? { ...prev, code: event.target.value } : prev))
            }
            style={{ marginRight: "0.5rem" }}
          />
          <label style={{ marginRight: "0.5rem" }}>
            <input
              type="checkbox"
              checked={editTrack.is_active}
              onChange={(event) =>
                setEditTrack((prev) =>
                  prev ? { ...prev, is_active: event.target.checked } : prev,
                )
              }
            />
            Active
          </label>
          <button type="button" onClick={handleSave}>
            Save
          </button>
        </div>
      )}
      <div style={{ marginTop: "1rem" }}>
        {tracks.map((track) => (
          <div
            key={track.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "0.5rem 0",
              borderBottom: "1px solid #f3f4f6",
            }}
          >
            <div>
              <strong>{track.name}</strong> · {track.code}
              <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                {track.is_active ? "Active" : "Disabled"}
              </div>
            </div>
            <button type="button" onClick={() => setEditTrack(track)}>
              Edit
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function QualityView({ api, onError }: { api: any; onError: (msg: string) => void }) {
  const [qualities, setQualities] = useState<Quality[]>([]);
  const [newQuality, setNewQuality] = useState({ name: "", height: "" });
  const [editQuality, setEditQuality] = useState<Quality | null>(null);

  const load = async () => {
    try {
      const data = await api.get<{ items: Quality[] }>("/admin/qualities");
      setQualities(data.items);
    } catch (err) {
      onError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    try {
      await api.post("/admin/qualities", {
        name: newQuality.name,
        height: Number(newQuality.height),
        is_active: true,
      });
      setNewQuality({ name: "", height: "" });
      load();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const handleSave = async () => {
    if (!editQuality) return;
    try {
      await api.patch(`/admin/qualities/${editQuality.id}`, {
        name: editQuality.name,
        height: editQuality.height,
        is_active: editQuality.is_active,
      });
      setEditQuality(null);
      load();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  return (
    <section>
      <h2>Qualities</h2>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "1rem" }}>
        <h3>Create quality</h3>
        <input
          placeholder="Name"
          value={newQuality.name}
          onChange={(event) =>
            setNewQuality((prev) => ({ ...prev, name: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        />
        <input
          placeholder="Height"
          value={newQuality.height}
          onChange={(event) =>
            setNewQuality((prev) => ({ ...prev, height: event.target.value }))
          }
          style={{ marginRight: "0.5rem" }}
        />
        <button type="button" onClick={handleCreate}>
          Create
        </button>
      </div>
      {editQuality && (
        <div
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "1rem",
            marginTop: "1rem",
          }}
        >
          <h3>Edit quality</h3>
          <input
            value={editQuality.name}
            onChange={(event) =>
              setEditQuality((prev) => (prev ? { ...prev, name: event.target.value } : prev))
            }
            style={{ marginRight: "0.5rem" }}
          />
          <input
            value={editQuality.height}
            onChange={(event) =>
              setEditQuality((prev) =>
                prev ? { ...prev, height: Number(event.target.value) } : prev,
              )
            }
            style={{ marginRight: "0.5rem" }}
          />
          <label style={{ marginRight: "0.5rem" }}>
            <input
              type="checkbox"
              checked={editQuality.is_active}
              onChange={(event) =>
                setEditQuality((prev) =>
                  prev ? { ...prev, is_active: event.target.checked } : prev,
                )
              }
            />
            Active
          </label>
          <button type="button" onClick={handleSave}>
            Save
          </button>
        </div>
      )}
      <div style={{ marginTop: "1rem" }}>
        {qualities.map((quality) => (
          <div
            key={quality.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "0.5rem 0",
              borderBottom: "1px solid #f3f4f6",
            }}
          >
            <div>
              <strong>{quality.name}</strong> · {quality.height}p
              <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>
                {quality.is_active ? "Active" : "Disabled"}
              </div>
            </div>
            <button type="button" onClick={() => setEditQuality(quality)}>
              Edit
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
