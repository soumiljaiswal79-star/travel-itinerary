import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Compass,
  ForkKnife,
  Globe2,
  Heart,
  Hotel,
  ImageOff,
  LogOut,
  MapPin,
  Menu,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Send,
  Share2,
  Sparkles,
  Trash2,
  Users,
  WandSparkles,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api, getImage, postJson, readSession, saveSession } from "./api";
import type {
  ApiSessionResponse,
  ItineraryDay,
  Member,
  Session,
  Stop,
  TravelStyle,
  Trip,
  TripForm,
  User,
} from "./types";

const interestOptions = ["Food & drink", "Sightseeing", "Nature", "Culture", "Adventure", "Shopping", "Art & design", "Wellness"];
const defaultForm = (): TripForm => ({
  destination: "",
  start_date: "",
  end_date: "",
  budget: 1800,
  currency: "USD",
  interests: ["Food & drink", "Sightseeing"],
  travel_style: "balanced",
  group_size: 2,
});

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function money(value: number, currency: string): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

function dates(start: string, end: string): string {
  const startDate = new Date(`${start}T12:00:00`);
  const endDate = new Date(`${end}T12:00:00`);
  const sameMonth = startDate.getMonth() === endDate.getMonth();
  const startText = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(startDate);
  const endText = new Intl.DateTimeFormat("en", { ...(sameMonth ? {} : { month: "short" }), day: "numeric", year: "numeric" }).format(endDate);
  return `${startText} – ${endText}`;
}

function getError(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    const wait = error.retryAfter
      ? `Try again in about ${error.retryAfter} seconds.`
      : "Check your Groq rate limits to see when requests reset.";
    return `Groq's free-tier request limit has been reached. ${wait} Avoid repeatedly retrying while the limit is active.`;
  }
  return messageOf(error);
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(Boolean(readSession()));

  useEffect(() => {
    if (!readSession()) return;
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {
        saveSession(null);
        setUser(null);
      })
      .finally(() => setCheckingAuth(false));
  }, []);

  useEffect(() => {
    const handleExpiredSession = () => setUser(null);
    window.addEventListener("wayfarer:session-expired", handleExpiredSession);
    return () => window.removeEventListener("wayfarer:session-expired", handleExpiredSession);
  }, []);

  const onAuthenticated = (nextUser: User, session: Session | null) => {
    saveSession(session);
    setUser(nextUser);
    setCheckingAuth(false);
  };

  if (checkingAuth) return <div className="loading-screen"><Compass size={28} /><span>Getting your trip space ready...</span></div>;
  if (!user) return <AuthScreen onAuthenticated={onAuthenticated} />;
  return <Planner user={user} onSignOut={() => { saveSession(null); setUser(null); }} />;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User, session: Session | null) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await postJson<ApiSessionResponse>(`/auth/${mode}`, { email, password });
      if (!result.session) {
        setNotice("Check your inbox to verify your email, then sign in to start planning.");
        setMode("login");
      } else {
        onAuthenticated(result.user, result.session);
      }
    } catch (requestError) {
      setError(getError(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-visual">
        <div className="brand brand-light"><span className="brand-mark"><Compass size={19} /></span> wayfarer</div>
        <div className="auth-visual-copy">
          <div className="eyebrow"><span className="eyebrow-dot" /> A little more wonder, a lot less planning</div>
          <h1>Your next<br />great story<br /><em>starts here.</em></h1>
          <p>Thoughtful itineraries, made for your kind of trip. Every detail, already considered.</p>
        </div>
        <div className="auth-quote"><span>“</span><div><p>The best days are the ones you didn't have to plan.</p><small>MAKE ROOM FOR THE MOMENT</small></div></div>
        <div className="auth-photo-credit">A different view, every day · WAYFARER</div>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="brand brand-dark"><span className="brand-mark"><Compass size={19} /></span> wayfarer</div>
          <div className="auth-heading">
            <p className="overline">{mode === "login" ? "WELCOME BACK" : "YOUR NEXT CHAPTER"}</p>
            <h2>{mode === "login" ? "Good to see you." : "Let's get going."}</h2>
            <p>{mode === "login" ? "Pick up right where your daydreams left off." : "Create your account and start exploring."}</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            <label>Email address<input type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="At least 8 characters" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required /></label>
            {error && <div className="form-message error-message">{error}</div>}
            {notice && <div className="form-message success-message">{notice}</div>}
            <button className="button button-dark auth-submit" disabled={busy}>{busy ? "One moment..." : mode === "login" ? "Sign in" : "Create account"}<ArrowRight size={17} /></button>
          </form>
          <div className="auth-switch">{mode === "login" ? "New around here?" : "Already have an account?"}{" "}<button onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); setNotice(""); }}>{mode === "login" ? "Create an account" : "Sign in"}</button></div>
          <div className="auth-footer"><span>Private by nature</span><span className="footer-dot" /> Your trips, your call <CircleHelp size={13} /></div>
        </div>
      </section>
    </main>
  );
}

function Planner({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showBuilder, setShowBuilder] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [search, setSearch] = useState("");

  const loadTrips = useCallback(async () => {
    setError("");
    try {
      const result = await api<Trip[]>("/trips");
      setTrips(result);
      setSelectedId((current) => current && result.some((trip) => trip.id === current) ? current : result[0]?.id ?? null);
    } catch (requestError) {
      setError(getError(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadTrips(); }, [loadTrips]);

  const selectedTrip = trips.find((trip) => trip.id === selectedId) ?? null;
  const visibleTrips = useMemo(() => trips.filter((trip) => trip.destination.toLowerCase().includes(search.toLowerCase()) || trip.title.toLowerCase().includes(search.toLowerCase())), [trips, search]);
  const updateTrip = (updated: Trip) => setTrips((current) => current.map((trip) => trip.id === updated.id ? updated : trip));
  const removeTrip = (id: string) => {
    setTrips((current) => current.filter((trip) => trip.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand"><div className="brand brand-dark"><span className="brand-mark"><Compass size={19} /></span> wayfarer</div><button className="icon-button mobile-close" onClick={() => setMobileNav(false)} aria-label="Close menu"><X size={18} /></button></div>
        <div className="sidebar-section-label">WORKSPACE</div>
        <button className="nav-item nav-item-active"><Compass size={17} /> My trips <span className="nav-count">{trips.length}</span></button>
        <button className="nav-item" onClick={() => setShowBuilder(true)}><Sparkles size={17} /> Plan a trip <Plus size={16} className="nav-plus" /></button>
        <div className="sidebar-section-label trips-section-label">YOUR PLANS <button className="icon-button mini" onClick={() => setShowBuilder(true)} aria-label="Add trip"><Plus size={15} /></button></div>
        <div className="sidebar-trip-list">
          {loading && <div className="sidebar-hint">Loading trips…</div>}
          {!loading && trips.length === 0 && <div className="sidebar-hint">Your next adventure starts here.</div>}
          {trips.slice(0, 6).map((trip) => <button key={trip.id} className={`trip-nav ${selectedId === trip.id ? "trip-nav-active" : ""}`} onClick={() => { setSelectedId(trip.id); setMobileNav(false); }}><span className="trip-nav-dot" /> <span>{trip.destination}</span><small>{trip.days.length}d</small></button>)}
        </div>
        <div className="sidebar-bottom">
          <div className="support-card"><span className="support-icon"><Heart size={16} /></span><div><b>A note from us</b><p>Travel is better when you leave room for wonder.</p></div></div>
          <div className="profile-button"><span className="avatar">{user.email.slice(0, 1).toUpperCase()}</span><span className="profile-name"><b>{user.email.split("@")[0]}</b><small>Personal space</small></span><button className="profile-menu icon-button" onClick={onSignOut} aria-label="Sign out"><LogOut size={16} /></button></div>
        </div>
      </aside>
      {mobileNav && <button className="nav-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu size={19} /></button>
          <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><b>{selectedTrip ? selectedTrip.destination : "My trips"}</b></div>
          <div className="topbar-actions"><div className="topbar-date"><span className="status-dot" /> YOUR NEXT ADVENTURE IS WAITING</div><button className="button button-dark topbar-create" onClick={() => setShowBuilder(true)}><Plus size={16} /> New trip</button></div>
        </header>
        <div className="page-scroll">
          <div className="content-wrap">
            {error && <div className="banner-error">{error}<button onClick={() => setError("")}><X size={15} /></button></div>}
            {loading ? <div className="loading-card"><Compass size={24} /> Gathering your journeys…</div> : selectedTrip ? (
              <TripWorkspace
                trip={selectedTrip}
                onUpdate={updateTrip}
                onDelete={() => removeTrip(selectedTrip.id)}
                onHome={() => setSelectedId(null)}
                canDelete={selectedTrip.role === "owner"}
              />
            ) : (
              <Dashboard
                trips={visibleTrips}
                search={search}
                setSearch={setSearch}
                onSelect={setSelectedId}
                onCreate={() => setShowBuilder(true)}
              />
            )}
          </div>
          <footer className="page-footer"><span>Made for the joy of getting there.</span><span>WAYFARER <span className="footer-dot" /> PLAN LIGHT, TRAVEL DEEP</span></footer>
        </div>
      </main>
      {showBuilder && <TripBuilder onClose={() => setShowBuilder(false)} onCreated={(trip) => { setTrips((current) => [trip, ...current]); setSelectedId(trip.id); setShowBuilder(false); }} />}
    </div>
  );
}

function Dashboard({ trips, search, setSearch, onSelect, onCreate }: {
  trips: Trip[];
  search: string;
  setSearch: (value: string) => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const upcoming = trips.filter((trip) => trip.end_date >= new Date().toISOString().slice(0, 10));
  return (
    <section className="dashboard">
      <div className="welcome-row">
        <div><p className="overline"><span className="overline-line" /> YOUR TRAVEL JOURNAL</p><h1>Somewhere<br /><em>is calling.</em></h1><p className="welcome-subtitle">A little daydream goes a long way. Where to next?</p></div>
        <div className="welcome-stamp"><span>GO SLOW.</span><span>SEE MORE.</span><Compass size={22} /></div>
      </div>
      <section className="inspiration-card">
        <RemoteImage query="Dolomites Italy mountain landscape morning" alt="Soft morning light over a mountain landscape" className="inspiration-image" />
        <div className="inspiration-scrim" />
        <div className="inspiration-content"><div className="inspiration-label"><span /> A LITTLE INSPIRATION</div><h2>The long way<br />is often the<br /><em>loveliest.</em></h2><p>Less rushing. More noticing.</p><button className="inspiration-button" onClick={onCreate}>Plan something lovely <ArrowRight size={15} /></button></div>
        <div className="inspiration-caption"><MapPin size={13} /> DOLOMITES, ITALY</div>
      </section>
      <section className="trips-overview">
        <div className="section-heading"><div><p className="overline">YOUR COLLECTION</p><h2>{upcoming.length ? "Trips on the horizon" : "Your journeys"}</h2></div><div className="collection-tools"><label className="search-field"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a trip..." /><span>/</span></label><button className="button button-outline" onClick={onCreate}><Plus size={15} /> New trip</button></div></div>
        {trips.length === 0 ? <EmptyTrips onCreate={onCreate} /> : <div className="trip-grid">{trips.map((trip, index) => <TripCard key={trip.id} trip={trip} index={index} onClick={() => onSelect(trip.id)} />)}</div>}
      </section>
      <div className="dashboard-note"><span className="note-line" /><p>Good plans make space for the unexpected.</p><span className="note-line" /></div>
    </section>
  );
}

function EmptyTrips({ onCreate }: { onCreate: () => void }) {
  return <div className="empty-state"><div className="empty-orbit"><Compass size={26} /></div><h3>No trips just yet</h3><p>Every great journey starts with a little curiosity.</p><button className="button button-dark" onClick={onCreate}><Sparkles size={15} /> Plan your first trip</button></div>;
}

function TripCard({ trip, index, onClick }: { trip: Trip; index: number; onClick: () => void }) {
  return (
    <button className={`trip-card trip-card-${index % 4}`} onClick={onClick}>
      <div className="trip-card-image-wrap"><RemoteImage query={`${trip.destination} travel landmark`} alt={`${trip.destination} landscape`} className="trip-card-image" /><span className="trip-card-day">{trip.days.length} DAYS</span><span className="trip-card-open"><ArrowUpRight size={16} /></span></div>
      <div className="trip-card-body"><div className="trip-card-place"><MapPin size={12} /> {trip.destination.toUpperCase()}</div><h3>{trip.title}</h3><div className="trip-card-meta"><span><CalendarDays size={13} /> {dates(trip.start_date, trip.end_date)}</span><span><Users size={13} /> {trip.group_size}</span></div><div className="trip-card-footer"><span>{trip.interests.slice(0, 2).join(" · ")}</span><span>{money(trip.total_estimated_cost, trip.currency)}</span></div></div>
    </button>
  );
}

function TripBuilder({ onClose, onCreated }: { onClose: () => void; onCreated: (trip: Trip) => void }) {
  const [form, setForm] = useState<TripForm>(defaultForm);
  const [refinement, setRefinement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(1);
  const setField = <K extends keyof TripForm>(key: K, value: TripForm[K]) => setForm((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const trip = await postJson<Trip>("/trips/generate", { ...form, refinement });
      onCreated(trip);
    } catch (requestError) {
      setError(getError(requestError));
    } finally {
      setBusy(false);
    }
  }

  function toggleInterest(interest: string) {
    setForm((current) => ({ ...current, interests: current.interests.includes(interest) ? current.interests.filter((item) => item !== interest) : [...current.interests, interest] }));
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="builder-modal" role="dialog" aria-modal="true" aria-labelledby="builder-heading">
        <header className="modal-header"><div className="brand brand-dark"><span className="brand-mark"><Compass size={18} /></span> wayfarer</div><button className="icon-button" onClick={onClose} disabled={busy} aria-label="Close trip planner"><X size={19} /></button></header>
        <div className="builder-intro"><div className="builder-step">A NEW ADVENTURE <span>0{step} / 02</span></div><h2 id="builder-heading">{step === 1 ? "Where shall we go?" : "Make it your kind of trip."}</h2><p>{step === 1 ? "Start with the place, and the rest will fall into place." : "A few details help us get the feeling just right."}</p><div className="step-track"><span className={step >= 1 ? "step-filled" : ""} /><span className={step >= 2 ? "step-filled" : ""} /></div></div>
        <form onSubmit={submit}>
          {step === 1 ? <div className="builder-fields">
            <label className="field-full">Where are you dreaming of?<span className="input-with-icon"><MapPin size={16} /><input autoFocus value={form.destination} onChange={(event) => setField("destination", event.target.value)} placeholder="A city, coast, or somewhere in between" required minLength={2} maxLength={120} /></span></label>
            <div className="field-row"><label>Arrive<input type="date" value={form.start_date} onChange={(event) => setField("start_date", event.target.value)} required /></label><label>Head home<input type="date" value={form.end_date} min={form.start_date} onChange={(event) => setField("end_date", event.target.value)} required /></label></div>
            <div className="field-row"><label>Budget for everyone<div className="input-prefix"><span>$</span><input type="number" value={form.budget} min={1} max={1000000} onChange={(event) => setField("budget", Number(event.target.value))} required /></div></label><label>Travelers<div className="stepper"><button type="button" onClick={() => setField("group_size", Math.max(1, form.group_size - 1))}>−</button><span>{form.group_size} <small>{form.group_size === 1 ? "person" : "people"}</small></span><button type="button" onClick={() => setField("group_size", Math.min(30, form.group_size + 1))}>+</button></div></label></div>
          </div> : <div className="builder-fields">
            <label className="field-full">What sounds like you?<div className="interest-list">{interestOptions.map((interest) => <button key={interest} type="button" className={`interest-chip ${form.interests.includes(interest) ? "interest-selected" : ""}`} onClick={() => toggleInterest(interest)}>{form.interests.includes(interest) && <Check size={13} />}{interest}</button>)}</div></label>
            <label className="field-full">Your travel rhythm<div className="style-options">{(["relaxed", "balanced", "packed"] as TravelStyle[]).map((style) => <button key={style} type="button" className={`style-option ${form.travel_style === style ? "style-active" : ""}`} onClick={() => setField("travel_style", style)}><span className="style-radio" /> <span><b>{style[0].toUpperCase() + style.slice(1)}</b><small>{style === "relaxed" ? "Slow mornings, room to wander" : style === "balanced" ? "A little bit of everything" : "Make every day count"}</small></span></button>)}</div></label>
            <label className="field-full">Anything else we should know? <textarea value={refinement} onChange={(event) => setRefinement(event.target.value)} placeholder="A favorite food, a pace to keep, a surprise to include…" rows={3} maxLength={800} /></label>
          </div>}
          {error && <div className="form-message error-message">{error}</div>}
          <div className="builder-actions">{step === 2 && <button type="button" className="button button-outline" onClick={() => setStep(1)}><ArrowLeft size={15} /> Back</button>}{step === 1 ? <button type="button" className="button button-dark builder-next" disabled={!form.destination || !form.start_date || !form.end_date || new Date(form.end_date) < new Date(form.start_date)} onClick={() => setStep(2)}>Next: make it yours <ArrowRight size={16} /></button> : <button className="button button-dark builder-next" disabled={busy || form.interests.length === 0}>{busy ? <><span className="button-spinner" /> Finding your way...</> : <><Sparkles size={16} /> Create my itinerary</>}</button>}</div>
          <div className="builder-footnote"><Sparkles size={13} /> A thoughtful first draft, made just for you.</div>
        </form>
      </section>
    </div>
  );
}

function TripWorkspace({ trip, onUpdate, onDelete, onHome, canDelete }: { trip: Trip; onUpdate: (trip: Trip) => void; onDelete: () => void; onHome: () => void; canDelete: boolean }) {
  const [dayIndex, setDayIndex] = useState(0);
  const [refinement, setRefinement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showShare, setShowShare] = useState(false);
  const [showTripEdit, setShowTripEdit] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedDay, setEditedDay] = useState<ItineraryDay>(trip.days[dayIndex]);
  const currentDay = trip.days[dayIndex];
  const isEditor = trip.role !== "viewer";
  const [activeAction, setActiveAction] = useState<"regenerate" | "day" | null>(null);

  useEffect(() => { setDayIndex((index) => Math.min(index, Math.max(0, trip.days.length - 1))); }, [trip.days.length]);
  useEffect(() => { setEditedDay(currentDay); setEditing(false); }, [currentDay]);
  useEffect(() => { setNotice(""); setError(""); }, [trip.id]);

  async function runRegeneration(kind: "regenerate" | "day") {
    if (!refinement.trim() && kind === "regenerate") {
      setError("Add a little guidance so the new plan feels different.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await postJson<Trip>(kind === "day" ? `/trips/${trip.id}/days/${currentDay.day_number}/regenerate` : `/trips/${trip.id}/regenerate`, { refinement });
      onUpdate(updated);
      setDayIndex(kind === "day" ? dayIndex : 0);
      setRefinement("");
      setActiveAction(null);
      setNotice(kind === "day" ? "This day has a fresh new plan." : "Your itinerary has been refreshed.");
    } catch (requestError) {
      setError(getError(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function saveEditedDay() {
    setBusy(true);
    setError("");
    try {
      const updated = await api<Trip>(`/trips/${trip.id}/days/${editedDay.day_number}`, { method: "PUT", body: JSON.stringify({ day: editedDay }) });
      onUpdate(updated);
      setEditing(false);
      setNotice("Your day is saved.");
    } catch (requestError) {
      setError(getError(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function deleteTrip() {
    if (!window.confirm(`Delete "${trip.title}"? This can't be undone.`)) return;
    try {
      await api<void>(`/trips/${trip.id}`, { method: "DELETE" });
      onDelete();
    } catch (requestError) {
      setError(getError(requestError));
    }
  }

  const saveTripChanges = async (changes: Partial<Trip>) => {
    try {
      const updated = await api<Trip>(`/trips/${trip.id}`, { method: "PATCH", body: JSON.stringify(changes) });
      onUpdate(updated);
      setShowTripEdit(false);
      setNotice("Trip details updated.");
    } catch (requestError) {
      setError(getError(requestError));
    }
  };

  return (
    <section className="trip-workspace">
      <div className="trip-hero">
        <RemoteImage query={`${trip.destination} landscape travel`} alt={`${trip.destination} landscape`} className="trip-hero-image" />
        <div className="trip-hero-overlay" />
        <div className="trip-hero-top"><button className="hero-back" onClick={onHome}><ArrowLeft size={15} /> All trips</button><div className="hero-owner-badge">{trip.role === "owner" ? "YOUR TRIP" : trip.role === "editor" ? "SHARED · EDITOR" : "SHARED · VIEWER"}</div></div>
        <div className="trip-hero-copy"><p className="trip-hero-place"><MapPin size={13} /> {trip.destination.toUpperCase()}</p><h1>{trip.title}</h1><p>{trip.summary}</p></div>
        <div className="trip-hero-bottom"><span><CalendarDays size={15} /> {dates(trip.start_date, trip.end_date)}</span><span><Users size={15} /> {trip.group_size} {trip.group_size === 1 ? "traveler" : "travelers"}</span><span><Sparkles size={15} /> {trip.travel_style} pace</span></div>
      </div>
      <div className="trip-stats"><div><span>PLANNED SPEND</span><b>{money(trip.total_estimated_cost, trip.currency)}</b><small>of {money(trip.budget, trip.currency)} budget</small></div><div className="stat-divider" /><div><span>ROOM TO WANDER</span><b>{money(Math.max(0, trip.budget - trip.total_estimated_cost), trip.currency)}</b><small>still in the budget</small></div><div className="stat-divider" /><div><span>YOUR TRIP</span><b>{trip.days.length} days <small>·</small> {trip.group_size} {trip.group_size === 1 ? "guest" : "guests"}</b><small>{trip.interests.slice(0, 3).join(" · ")}</small></div><div className="stats-actions">{isEditor && <button className="button button-outline compact-button" onClick={() => setShowTripEdit(true)}>Edit trip</button>}<button className="icon-button" onClick={() => setShowShare(true)} title="Share trip"><Share2 size={17} /></button>{canDelete && <button className="icon-button danger-icon" onClick={() => void deleteTrip()} title="Delete trip"><Trash2 size={16} /></button>}</div></div>
      {error && <div className="banner-error">{error}<button onClick={() => setError("")}><X size={15} /></button></div>}{notice && <div className="banner-success"><Check size={15} />{notice}<button onClick={() => setNotice("")}><X size={15} /></button></div>}
      <div className="itinerary-layout">
        <aside className="day-rail"><div className="rail-heading"><span>YOUR ITINERARY</span><span>{trip.days.length} DAYS</span></div>{trip.days.map((day, index) => <button key={day.day_number} className={`day-tab ${dayIndex === index ? "day-tab-active" : ""}`} onClick={() => setDayIndex(index)}><span className="day-tab-num">{String(day.day_number).padStart(2, "0")}</span><span className="day-tab-text"><b>{new Intl.DateTimeFormat("en", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${day.date}T12:00:00`))}</b><small>{day.theme}</small></span><ChevronDown size={14} /></button>)}
          <div className="rail-budget"><span>TRIP BUDGET</span><div className="budget-bar"><span style={{ width: `${Math.min(100, trip.total_estimated_cost / trip.budget * 100)}%` }} /></div><b>{Math.round(trip.total_estimated_cost / trip.budget * 100)}% <small>planned</small></b></div>
        </aside>
        <div className="day-content">
          {currentDay && <><div className="day-heading"><div><p className="overline"><span className="overline-line" /> DAY {String(currentDay.day_number).padStart(2, "0")} <span className="day-heading-date">· {new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" }).format(new Date(`${currentDay.date}T12:00:00`))}</span></p><h2>{currentDay.theme}</h2><p className="day-summary">{currentDay.stops.length} moments, thoughtfully arranged · {money(currentDay.estimated_cost, trip.currency)}</p></div><div className="day-controls">{isEditor && !editing && <button className="icon-button" title="Edit day" onClick={() => setEditing(true)}><MoreHorizontal size={19} /></button>}{isEditor && <button className="button button-outline compact-button" onClick={() => { setActiveAction(activeAction === "day" ? null : "day"); setError(""); }}><RefreshCw size={14} /> Refresh day</button>}</div></div>
            {activeAction === "day" && <div className="refine-panel"><div><Sparkles size={16} /><span>What should feel different?</span></div><input value={refinement} onChange={(event) => setRefinement(event.target.value)} placeholder="More time outdoors, a quieter lunch..." maxLength={800} /><button className="button button-dark compact-button" disabled={busy} onClick={() => void runRegeneration("day")}>{busy ? "Working..." : "Refresh day"}<ArrowRight size={14} /></button></div>}
            {editing && <div className="edit-day-banner"><span><WandSparkles size={15} /> Edit your day</span><div><button className="button button-outline compact-button" onClick={() => { setEditedDay(currentDay); setEditing(false); }}>Cancel</button><button className="button button-dark compact-button" disabled={busy} onClick={() => void saveEditedDay()}>{busy ? "Saving..." : "Save day"}<Check size={14} /></button></div></div>}
            <div className="timeline">{currentDay.stops.map((stop, index) => <StopCard key={`${stop.time}-${index}`} stop={stop} currency={trip.currency} last={index === currentDay.stops.length - 1} editing={editing} onChange={(updated) => setEditedDay((current) => ({ ...current, stops: current.stops.map((item, stopIndex) => stopIndex === index ? updated : item) }))} />)}</div>
            <div className="logistics-grid"><div className="logistics-card"><span className="logistics-icon lodging-icon"><Hotel size={16} /></span><div className="logistics-label">A GOOD PLACE TO LAND</div><h3>{currentDay.accommodation.name}</h3><p>{currentDay.accommodation.neighborhood} · {currentDay.accommodation.notes}</p><b>{money(currentDay.accommodation.nightly_cost, trip.currency)} <small>/ night</small></b></div><div className="logistics-card"><span className="logistics-icon transport-icon"><ArrowRight size={16} /></span><div className="logistics-label">GETTING AROUND</div><h3>Take it in stride</h3><div className="transport-list">{currentDay.transportation.map((item) => <span key={item}><span />{item}</span>)}</div></div></div>
            <div className="day-cost-note"><div><span className="cost-spark"><Sparkles size={14} /></span><span>Today's thoughtful estimate</span></div><b>{money(currentDay.estimated_cost, trip.currency)}</b></div>
          </>}
        </div>
      </div>
      {isEditor && <section className="regenerate-cta"><div className="regenerate-icon"><Sparkles size={18} /></div><div className="regenerate-copy"><span>MAKE IT MORE YOU</span><h3>Want to see another version?</h3><p>Keep the same dates, budget, and things you love. Just add a new thought.</p></div><div className="regenerate-input-wrap"><input value={refinement} onChange={(event) => setRefinement(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && refinement.trim()) void runRegeneration("regenerate"); }} placeholder="Try a different angle..." maxLength={800} /><button className="button button-dark compact-button" disabled={busy || !refinement.trim()} onClick={() => void runRegeneration("regenerate")}>{busy ? "Reimagining..." : "Reimagine trip"}<Send size={14} /></button></div></section>}
      {showShare && <ShareModal trip={trip} onClose={() => setShowShare(false)} onError={setError} />}
      {showTripEdit && <EditTripModal trip={trip} onClose={() => setShowTripEdit(false)} onSave={saveTripChanges} />}
    </section>
  );
}

function StopCard({ stop, currency, last, editing, onChange }: { stop: Stop; currency: string; last: boolean; editing: boolean; onChange: (stop: Stop) => void }) {
  const icon = stop.kind === "dining" ? <ForkKnife size={15} /> : stop.kind === "experience" ? <Sparkles size={15} /> : <MapPin size={15} />;
  const kindLabel = stop.kind === "dining" ? "A GOOD TABLE" : stop.kind === "experience" ? "SOMETHING SPECIAL" : "WORTH THE STOP";
  return (
    <article className={`timeline-item ${last ? "timeline-last" : ""}`}>
      <div className="timeline-time"><b>{stop.time.slice(0, 5)}</b><span>{icon}</span></div>
      <div className="timeline-connector"><span className={`timeline-dot dot-${stop.kind}`} />{!last && <span className="timeline-line" />}</div>
      <div className="stop-card"><div className="stop-image-wrap"><RemoteImage query={`${stop.title} ${stop.location}`} alt={stop.title} className="stop-image" /><span className="stop-image-label">{kindLabel}</span><span className="stop-image-icon">{icon}</span></div>
        <div className="stop-card-body">{editing ? <div className="stop-edit-fields"><input aria-label="Activity title" value={stop.title} onChange={(event) => onChange({ ...stop, title: event.target.value })} /><textarea aria-label="Activity description" value={stop.description} onChange={(event) => onChange({ ...stop, description: event.target.value })} rows={2} /><input aria-label="Location" value={stop.location} onChange={(event) => onChange({ ...stop, location: event.target.value })} /><input aria-label="Start time" type="time" value={stop.time.slice(0, 5)} onChange={(event) => onChange({ ...stop, time: event.target.value })} /></div> : <><div className="stop-title-row"><h3>{stop.title}</h3><span className="stop-cost">{money(stop.estimated_cost, currency)}</span></div><p>{stop.description}</p><div className="stop-meta"><span><MapPin size={12} /> {stop.location}</span><span><Clock3 size={12} /> {Math.floor(stop.duration_minutes / 60) ? `${Math.floor(stop.duration_minutes / 60)}h ` : ""}{stop.duration_minutes % 60 ? `${stop.duration_minutes % 60}m` : ""}</span></div></>}</div>
      </div>
    </article>
  );
}

function RemoteImage({ query, alt, className }: { query: string; alt: string; className: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setUrl(null);
    setFailed(false);
    getImage(query)
      .then((imageUrl) => { if (alive) setUrl(imageUrl); })
      .catch(() => { if (alive) setUrl(null); });
    return () => { alive = false; };
  }, [query]);
  if (url && !failed) return <img className={className} src={url} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
  return <div className={`${className} image-placeholder`} role="img" aria-label={`${alt} image unavailable`}><ImageOff size={17} /><span>WAYFARER</span></div>;
}

function ShareModal({ trip, onClose, onError }: { trip: Trip; onClose: () => void; onError: (message: string) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"editor" | "viewer">("editor");
  const [members, setMembers] = useState<Member[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const loadMembers = useCallback(async () => {
    try { setMembers(await api<Member[]>(`/trips/${trip.id}/members`)); } catch (requestError) { setError(getError(requestError)); }
  }, [trip.id]);
  useEffect(() => { void loadMembers(); }, [loadMembers]);
  async function addMember(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await postJson<Member>(`/trips/${trip.id}/members`, { email, role });
      setEmail("");
      setNotice("Your invitation is ready. They'll see this trip the next time they sign in.");
      await loadMembers();
    } catch (requestError) { setError(getError(requestError)); onError(getError(requestError)); }
    finally { setBusy(false); }
  }
  async function removeMember(id: string) {
    try {
      await api<void>(`/trips/${trip.id}/members/${id}`, { method: "DELETE" });
      await loadMembers();
    } catch (requestError) { setError(getError(requestError)); }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="small-modal" role="dialog" aria-modal="true" aria-labelledby="share-title"><div className="small-modal-top"><span className="modal-badge"><Users size={16} /></span><button className="icon-button" onClick={onClose} aria-label="Close sharing dialog"><X size={18} /></button></div><h2 id="share-title">A trip is better together.</h2><p>Invite a travel companion to plan this journey with you.</p>{trip.role === "owner" ? <form className="share-form" onSubmit={(event) => void addMember(event)}><label>EMAIL ADDRESS<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="friend@example.com" /></label><label>THEY CAN<select value={role} onChange={(event) => setRole(event.target.value as "editor" | "viewer")}><option value="editor">Edit this trip</option><option value="viewer">View only</option></select></label><button className="button button-dark" disabled={busy}>{busy ? "Adding..." : "Add to the trip"}<ArrowRight size={15} /></button></form> : <div className="share-readonly">You're a {trip.role} on this shared trip. Ask the owner to invite other travelers.</div>}{error && <div className="form-message error-message">{error}</div>}{notice && <div className="form-message success-message">{notice}</div>}<div className="member-list"><div className="member-list-heading">TRAVEL COMPANIONS <span>{members.length}</span></div>{members.length ? members.map((member) => <div className="member-row" key={member.user_id}><span className="avatar member-avatar">{(member.profiles?.display_name || member.profiles?.email || "?").slice(0, 1).toUpperCase()}</span><span><b>{member.profiles?.display_name || member.profiles?.email || "Trip companion"}</b><small>{member.role === "editor" ? "Can edit" : "Can view"}</small></span>{trip.role === "owner" && <button className="icon-button" onClick={() => void removeMember(member.user_id)} aria-label="Remove trip companion"><X size={15} /></button>}</div>) : <div className="member-empty">No collaborators yet.</div>}</div><div className="share-safe"><Globe2 size={14} /> Only people you invite can see this trip.</div></section></div>;
}

function EditTripModal({ trip, onClose, onSave }: { trip: Trip; onClose: () => void; onSave: (changes: Partial<Trip>) => Promise<void> }) {
  const [title, setTitle] = useState(trip.title);
  const [budget, setBudget] = useState(trip.budget);
  const [busy, setBusy] = useState(false);
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><form className="small-modal edit-trip-modal" onSubmit={async (event) => { event.preventDefault(); setBusy(true); await onSave({ title, budget }); setBusy(false); }}><div className="small-modal-top"><span className="modal-badge"><WandSparkles size={16} /></span><button type="button" className="icon-button" onClick={onClose} aria-label="Close edit trip"><X size={18} /></button></div><h2>A few trip details.</h2><p>Change the title or adjust your total budget.</p><label>TRIP NAME<input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} maxLength={160} /></label><label>TOTAL BUDGET ({trip.currency})<input type="number" min={1} value={budget} onChange={(event) => setBudget(Number(event.target.value))} required /></label><button className="button button-dark" disabled={busy}>{busy ? "Saving..." : "Save trip details"}<Check size={15} /></button></form></div>;
}

export default App;
