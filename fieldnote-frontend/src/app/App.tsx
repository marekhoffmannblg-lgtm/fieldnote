import { Fragment, useState, useEffect, useRef, type ReactNode } from "react";
import catalogData from "../data/generated/catalog.json";
import { apiRequest } from "../api/client";
import type { EvidenceItemV1, ProductMetricsV1, SourceContributionV1 } from "../api/contracts";
import { parseFieldnoteRoute, routeForPage, type FieldnotePage } from "../routes/navigation";
import {
  Package,
  Search,
  Zap,
  HelpCircle,
  Menu,
  X,
  ChevronRight,
  ChevronDown,
  RotateCcw,
  Plus,
  GitCompare,
  ExternalLink,
  Filter,
  CheckSquare,
  Square,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  ArrowLeft,
  RefreshCw,
  Link2,
  FileText,
  BarChart2,
  ChevronUp,
  Layers,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
type Page = FieldnotePage;

type ProductStatus = "ready" | "analysis_running" | "analysis_failed" | "refresh_recommended";

interface Product {
  id: string;
  slug: string;
  brand: string;
  name: string;
  model: string;
  status: ProductStatus;
  coverage: number | null;
  zrodla: number | null;
  braki: number | null;
  marketplace: string[];
  lastRun: string | null;
  fieldsTotal: number;
  fieldsCompleted: number;
  conflicts: number;
  metrics?: Partial<ProductMetricsV1>;
  category: string;
  benchmarkCategory: string;
  statusReason?: string;
  statusUpdatedAt?: string | null;
}

interface CatalogProduct {
  brand: string;
  model: string;
  slug: string;
  status: ProductStatus;
  coverage: number | null;
  fields_total: number;
  fields_completed: number;
  sources_count: number;
  source_counts?: {
    selected_count?: number;
    fetched_count?: number;
    fetch_failed_count?: number;
    cleaned_count?: number;
    assigned_count?: number;
    unattached_count?: number;
    used_count?: number;
  };
  missing_fields_count: number;
  conflicts_count: number;
  metrics?: Partial<ProductMetricsV1>;
  updated_at: string;
  marketplaces?: string[];
  product_id?: string;
  category?: string;
  category_slug?: string;
  benchmark_category?: string;
  status_reason?: string;
  status_updated_at?: string;
}

interface FieldEvidence extends Partial<EvidenceItemV1> {
  source_id: string;
  source_type: string;
  source_url: string;
  original_url: string;
  offer_id: string;
  domain: string;
  fetched_at: string;
  raw_snapshot_path: string;
  clean_snapshot_path: string;
  content_hash: string;
  source_status: "unchecked" | "active" | "unavailable";
  value: string;
  excerpt: string;
  evidence: string;
}

interface ProductField {
  field_name: string;
  value: string;
  status: string;
  confidence: string;
  locked: boolean;
  validation_status: string;
  evidence: FieldEvidence[];
  source_id: string;
  source_type: string;
  source_url: string;
  excerpt: string;
  provenance?: {
    independent_confirmations_count?: number;
    total_sources_count?: number;
    content_families_count?: number;
    has_conflict?: boolean;
  };
}

interface ProductDetailSnapshot extends CatalogProduct {
  group_key: string;
  fields: ProductField[];
  sources?: Array<{
    source_id: string;
    marketplace: string;
    source_type: string;
  }>;
}

interface ProductSourceField {
  field_name: string;
  value: string;
  excerpt: string;
}

interface ProductSource {
  source_id: string;
  offer_id: string;
  title: string;
  marketplace: string;
  source_type: string;
  role: "primary" | "supplementary" | "manufacturer" | "fetched_but_unattached" | "failed" | "duplicate" | "rejected";
  selected: boolean;
  fetched: boolean;
  cleaned: boolean;
  attached: boolean;
  used_in_benchmark: boolean;
  original_url: string;
  canonical_url: string;
  domain: string;
  price: string;
  price_source: string;
  seller: { name: string; rating: string; reviews_count: string };
  source_status: "active" | "unavailable" | "unchecked";
  fetch_status: "fetched" | "failed" | "skipped";
  cleaner_status: "cleaned" | "not_cleaned" | "unavailable";
  fetch_error: string;
  first_fetched_at: string;
  last_fetched_at: string;
  related_run_dates: string[];
  fields_count: number;
  used_fields: ProductSourceField[];
  offer_quality: { score: number | null; reasons: string[] };
  raw_snapshot_path: string;
  clean_snapshot_path: string;
  snapshot_available: boolean;
  content_hash: string;
  invalid_seller_removed: boolean;
  contribution?: SourceContribution;
}

interface ProductSourcesResponse {
  product_slug: string;
  total: number;
  selected_count: number;
  fetched_count: number;
  failed_count: number;
  attached_count: number;
  unattached_count: number;
  duplicate_count: number;
  rejected_count: number;
  primary_count: number;
  supplementary_count: number;
  manufacturer_count: number;
  unavailable_count: number;
  prices_recovered: number;
  invalid_sellers_removed: number;
  accounted_selected_count: number;
  sources: ProductSource[];
}

interface SourceSnapshotResponse {
  product_slug: string;
  source_id: string;
  snapshot_path: string;
  snapshot_type: string;
  content: string;
}

interface ContributionField {
  field_name: string;
  value: string;
  excerpt: string;
}

interface SourceContribution extends SourceContributionV1 {
  unique_fields_contributed: ContributionField[];
  confirmed_fields: ContributionField[];
  conflicting_fields: ContributionField[];
  rejected_evidence: ContributionField[];
  final_fields_used: ContributionField[];
}

interface SourceContributionResponse {
  product_slug: string;
  source_id: string;
  title: string;
  summary: {
    unique_fields_contributed: number;
    confirmed_fields: number;
    conflicting_fields: number;
    rejected_evidence: number;
    final_fields_used: number;
  };
  contribution: SourceContribution;
  zero_contribution: boolean;
  message: string;
}

interface AnalysisStatus {
  product_slug: string;
  group_key: string;
  status: ProductStatus;
  sources_total: number;
  sources_with_snapshot: number;
  unprocessed_source_ids: string[];
  uncleaned_offer_ids: string[];
  open_fields: number;
  can_analyze_saved_data: boolean;
  uses_network_by_default: boolean;
}

interface BenchmarkResponse {
  product_slug: string;
  benchmark_category: string;
  models: Array<{
    slug: string;
    group_key: string;
    brand: string;
    model: string;
    coverage: number | null;
    values: Record<string, { value: string; status: string; confidence: string }>;
  }>;
  fields: string[];
  has_comparison: boolean;
}

interface PreviewOffer {
  offer_id: string;
  title: string;
  url: string;
  seller_name: string | null;
  seller_type: string | null;
  seller_rating: string | number | null;
  seller_reviews_count: string | number | null;
  price: string | null;
  currency: string | null;
  condition: string | null;
  sponsored: boolean | null;
  brand_match: boolean;
  model_match: boolean;
  accepted: boolean;
  already_known: boolean;
  is_accessory: boolean;
  product_type: "stroller" | "accessory" | "unknown";
  match_status: "exact_match" | "uncertain" | "rejected";
  rejection_reason: string | null;
  duplicate_count: number;
  source_group: "primary_source" | "supplementary_source" | null;
  offer_quality: {
    score: number;
    level: "high" | "medium" | "low";
    reasons: string[];
  };
}

interface ManufacturerSource {
  source_id: string;
  title: string;
  source_type: string;
  type_label: string;
  domain: string;
  url: string;
  model_match: boolean;
  match_status: "matched" | "uncertain" | "rejected" | "unavailable";
}

interface PreviewResponse {
  status: "ok";
  mode: "local_cached_listing" | "live_firecrawl";
  brand: string;
  model: string;
  requested_brand: string;
  requested_model: string;
  normalized_brand: string;
  normalized_model: string;
  search_query: string;
  preview_cache_key: string;
  offers: PreviewOffer[];
  manufacturer_sources: ManufacturerSource[];
  summary: Record<string, number | boolean | string>;
  preview_diagnostics: {
    query: string;
    cache_key: string;
    cache_hit: boolean;
    previous_product_slug: string;
    current_product_slug: string;
    exact_count: number;
    supplementary_count: number;
    accessory_count: number;
    uncertain_count: number;
    titles: string[];
  };
}

interface ApiRun {
  run_id: string;
  brand: string;
  model: string;
  status: "queued" | "running" | "succeeded" | "success" | "partial" | "failed" | "timed_out" | "cancelled" | "interrupted";
  current_step: string;
  progress: number;
  started_at: string | null;
  finished_at: string | null;
  error: string;
  logs_tail: string[];
  product_slug: string;
  snapshot_updated: boolean;
  pipeline_status?: "success" | "partial" | "failed" | "preview";
  refresh?: RefreshSummary;
  analysis?: { refresh_sources?: boolean; used_sources?: string[]; fields_changed?: number; coverage_before?: number | null; coverage_after?: number | null };
  run_type?: "research" | "refresh" | "reanalysis" | "migration";
  retry_of?: string | null;
  created_at?: string;
  sources_selected?: number;
  sources_fetched?: number;
  sources_failed?: number;
  sources_attached?: number;
  coverage_before?: number | null;
  coverage_after?: number | null;
  changed_fields?: string[];
}

interface RefreshSummary {
  mode?: "incremental" | "full_reanalysis";
  history_path?: string;
  new_sources?: number;
  changed_sources?: number;
  unavailable_sources?: number;
  fields_changed?: number;
  coverage_before?: number | null;
  coverage_after?: number | null;
}

interface RefreshHistoryEntry {
  version: string;
  run_id: string;
  mode: "incremental" | "full_reanalysis" | "analysis";
  started_at: string;
  finished_at: string | null;
  sources_before: number;
  sources_after: number;
  new_sources: string[];
  changed_sources: string[];
  unavailable_sources: string[];
  fields_changed: string[];
  coverage_before: number | null;
  coverage_after: number | null;
}

interface HistorySnapshot {
  version: string;
  fields: Array<{ field_name: string; value: string; status: string }>;
}

// ─── Data ─────────────────────────────────────────────────────────────────────
const productModules = import.meta.glob("../data/generated/products/*.json", {
  eager: true,
  import: "default",
}) as Record<string, ProductDetailSnapshot>;

const PRODUCT_DETAILS: Record<string, ProductDetailSnapshot> = Object.fromEntries(
  Object.entries(productModules).map(([path, product]) => [path.split("/").pop()?.replace(".json", "") || "", product]),
);

const DEVELOPER_MODE = import.meta.env.VITE_DEVELOPER_MODE === "1";

const statusFromSnapshot = (status: CatalogProduct["status"]): ProductStatus => {
  return status;
};

const PRODUCTS: Product[] = (catalogData as CatalogProduct[]).map((product) => ({
  id: product.slug,
  slug: product.slug,
  brand: product.brand,
  name: product.model,
  model: product.model,
  status: statusFromSnapshot(product.status),
  coverage: product.coverage,
  zrodla: product.source_counts?.used_count ?? product.sources_count,
  braki: product.missing_fields_count,
  marketplace: product.marketplaces || [],
  lastRun: product.updated_at || null,
  fieldsTotal: product.fields_total,
  fieldsCompleted: product.fields_completed,
  conflicts: product.conflicts_count,
  metrics: product.metrics,
  category: product.category || "Bez kategorii",
  benchmarkCategory: product.benchmark_category || "Bez podkategorii",
  statusReason: product.status_reason || "",
  statusUpdatedAt: product.status_updated_at || product.updated_at || null,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────
function coverageColor(v: number) {
  if (v >= 65) return "text-emerald-700 bg-emerald-50";
  if (v >= 50) return "text-amber-700 bg-amber-50";
  return "text-red-700 bg-red-50";
}

function statusBadge(s: ProductStatus) {
  const map: Record<ProductStatus, { label: string; cls: string }> = {
    ready: { label: "Gotowy", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    analysis_running: { label: "Analiza w toku", cls: "bg-blue-50 text-blue-700 border-blue-200" },
    analysis_failed: { label: "Błąd analizy", cls: "bg-red-50 text-red-700 border-red-200" },
    refresh_recommended: { label: "Wymaga odświeżenia", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  };
  return map[s];
}

function statusTooltip(product: Product) {
  if (product.status === "ready") return `Gotowy: ostatnia udana analiza ${product.statusUpdatedAt || product.lastRun || "—"}.`;
  if (product.status === "refresh_recommended") return `Wymaga odświeżenia: ${product.statusReason || "brak użytecznych lokalnych źródeł lub nieukończona analiza"}.`;
  if (product.status === "analysis_failed") return `Błąd analizy: ${product.statusReason || "sprawdź szczegóły w Historii"}.`;
  return "Analiza produktu jest w toku.";
}

function runStatusIcon(s: string) {
  if (s === "sukces") return <CheckCircle2 size={14} className="text-emerald-600" />;
  if (s === "blad") return <XCircle size={14} className="text-red-500" />;
  return <Clock size={14} className="text-amber-500" />;
}

// ─── Coverage Bar ─────────────────────────────────────────────────────────────
function CoverageBar({ value }: { value: number }) {
  const color = value >= 65 ? "bg-emerald-500" : value >= 50 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`text-xs font-mono font-medium px-1.5 py-0.5 rounded ${coverageColor(value)}`}>
        {value}%
      </span>
    </div>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
const NAV_ITEMS: { id: Page; label: string; icon: ReactNode }[] = [
  { id: "produkty", label: "Produkty", icon: <Package size={15} /> },
  { id: "research", label: "Research", icon: <Search size={15} /> },
  { id: "uruchomienia", label: "Uruchomienia", icon: <Zap size={15} /> },
  { id: "pomoc", label: "Pomoc", icon: <HelpCircle size={15} /> },
];

function Sidebar({
  current,
  onNav,
  collapsed,
}: {
  current: Page;
  onNav: (p: Page) => void;
  collapsed: boolean;
}) {
  const active = (id: Page) =>
    (current === id || ((current === "produkt-szczegoly" || current === "produkt-zrodla") && id === "produkty"))
      ? "bg-sidebar-accent text-sidebar-primary font-medium"
      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground";

  return (
    <aside
      className="flex flex-col border-r border-sidebar-border bg-sidebar h-full"
      style={{ width: collapsed ? 0 : 208, minWidth: collapsed ? 0 : 208, overflow: "hidden", transition: "width 200ms ease, min-width 200ms ease" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-sidebar-border">
        <div className="w-6 h-6 rounded bg-primary flex items-center justify-center flex-shrink-0">
          <BarChart2 size={13} className="text-white" />
        </div>
        <span className="text-sm font-semibold tracking-tight text-foreground whitespace-nowrap">FIELDNOTE</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onNav(item.id)}
            className={`flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors w-full text-left whitespace-nowrap ${active(item.id)}`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-sidebar-border">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary flex-shrink-0" aria-hidden="true">
            <BarChart2 size={12} />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-foreground whitespace-nowrap">Tryb lokalny</p>
            <p className="text-xs text-muted-foreground whitespace-nowrap">Dane zapisane lokalnie</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ─── Page: Produkty ───────────────────────────────────────────────────────────
function PageProdukty({ onDetail, onResearch }: { onDetail: (id: string) => void; onResearch: () => void }) {
  const [query, setQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("wszystkie");
  const [filterBrand, setFilterBrand] = useState<string>("wszystkie");
  const [filterCategory, setFilterCategory] = useState<string>("wszystkie");
  const [filterBenchmarkCategory, setFilterBenchmarkCategory] = useState<string>("wszystkie");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showFilter, setShowFilter] = useState(false);

  const filtered = PRODUCTS.filter((p) => {
    const q = query.toLowerCase();
    const matchQ = p.name.toLowerCase().includes(q) || p.brand.toLowerCase().includes(q);
    const matchS = filterStatus === "wszystkie" || p.status === filterStatus;
    const matchBrand = filterBrand === "wszystkie" || p.brand === filterBrand;
    const matchCategory = filterCategory === "wszystkie" || p.category === filterCategory;
    const matchBenchmarkCategory = filterBenchmarkCategory === "wszystkie" || p.benchmarkCategory === filterBenchmarkCategory;
    return matchQ && matchS && matchBrand && matchCategory && matchBenchmarkCategory;
  });
  const brands = [...new Set(PRODUCTS.map((product) => product.brand))].sort((a, b) => a.localeCompare(b, "pl"));
  const categories = [...new Set(PRODUCTS.map((product) => product.category))].sort((a, b) => a.localeCompare(b, "pl"));
  const benchmarkCategories = [...new Set(PRODUCTS.map((product) => product.benchmarkCategory))].sort((a, b) => a.localeCompare(b, "pl"));
  const grouped = filtered.reduce<Record<string, Product[]>>((groups, product) => {
    const key = `${product.brand} / ${product.category} / ${product.benchmarkCategory}`;
    (groups[key] ||= []).push(product);
    return groups;
  }, {});

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 5) next.add(id);
      return next;
    });
  };

  const allChecked = filtered.length > 0 && filtered.every((p) => selected.has(p.id));

  const toggleAll = () => {
    if (allChecked) {
      setSelected(new Set());
    } else {
      const toAdd = filtered.slice(0, 5).map((p) => p.id);
      setSelected(new Set(toAdd));
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-card flex items-center justify-between gap-4 flex-shrink-0">
        <div>
          <h1 className="text-base font-semibold text-foreground">Produkty</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{PRODUCTS.length} produktów w katalogu</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size >= 2 && (
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded bg-card text-foreground hover:bg-muted transition-colors">
              <GitCompare size={13} />
              Porównaj wybrane ({selected.size})
            </button>
          )}
          <button onClick={onResearch} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors">
            <Plus size={13} />
            Nowy research
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="px-6 py-3 border-b border-border bg-card flex flex-wrap items-center gap-3 flex-shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-input-background border border-border rounded outline-none focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground"
            placeholder="Szukaj produktu..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select value={filterBrand} onChange={(event) => setFilterBrand(event.target.value)} className="px-2.5 py-1.5 text-xs border border-border rounded bg-card text-foreground outline-none">
          <option value="wszystkie">Wszystkie marki</option>
          {brands.map((brand) => <option key={brand} value={brand}>{brand}</option>)}
        </select>
        <select value={filterCategory} onChange={(event) => setFilterCategory(event.target.value)} className="max-w-44 px-2.5 py-1.5 text-xs border border-border rounded bg-card text-foreground outline-none">
          <option value="wszystkie">Wszystkie kategorie</option>
          {categories.map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
        <select value={filterBenchmarkCategory} onChange={(event) => setFilterBenchmarkCategory(event.target.value)} className="max-w-44 px-2.5 py-1.5 text-xs border border-border rounded bg-card text-foreground outline-none">
          <option value="wszystkie">Wszystkie podkategorie</option>
          {benchmarkCategories.map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
        <div className="relative">
          <button
            onClick={() => setShowFilter(!showFilter)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border rounded transition-colors ${showFilter ? "border-primary/40 bg-accent text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >
            <Filter size={12} />
            Status
            <ChevronDown size={11} />
          </button>
          {showFilter && (
            <div className="absolute top-full left-0 mt-1 w-44 bg-card border border-border rounded shadow-lg z-20 py-1">
              {["wszystkie", "ready", "analysis_running", "analysis_failed", "refresh_recommended"].map((s) => (
                <button
                  key={s}
                  onClick={() => { setFilterStatus(s); setShowFilter(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors capitalize ${filterStatus === s ? "text-primary font-medium" : "text-foreground"}`}
                >
                  {s === "wszystkie" ? "Wszystkie" : statusBadge(s as ProductStatus).label}
                </button>
              ))}
            </div>
          )}
        </div>
        {selected.size > 0 && (
          <span className="text-xs text-muted-foreground">
            Zaznaczono: <span className="font-medium text-foreground">{selected.size}</span> / 5
          </span>
        )}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-border bg-muted/50">
              <th className="w-8 px-4 py-2.5 text-left">
                <button onClick={toggleAll} className="text-muted-foreground hover:text-foreground">
                  {allChecked ? <CheckSquare size={13} /> : <Square size={13} />}
                </button>
              </th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Produkt</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Kategoria</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Coverage</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Użyte źródła</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Braki</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Marketplace</th>
              <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">Akcja</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([groupLabel, products]) => (
              <Fragment key={groupLabel}>
                <tr className="bg-muted/30 border-y border-border"><td colSpan={9} className="px-4 py-2 text-[11px] font-medium text-muted-foreground">{groupLabel}</td></tr>
                {products.map((p) => {
              const badge = statusBadge(p.status);
              const isSelected = selected.has(p.id);
              return (
                <tr
                  key={p.id}
                  className={`border-b border-border transition-colors ${isSelected ? "bg-accent/30" : "hover:bg-muted/30"}`}
                >
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => toggle(p.id)}
                      className={`transition-colors ${isSelected ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}
                    >
                      {isSelected ? <CheckSquare size={13} /> : <Square size={13} />}
                    </button>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-foreground">{p.name}</div>
                    <div className="text-muted-foreground mt-0.5 font-normal text-[11px]">{p.brand}</div>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground"><div>{p.category}</div><div className="mt-0.5">{p.benchmarkCategory}</div></td>
                  <td className="px-3 py-2.5">
                    <span title={statusTooltip(p)} className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-medium ${badge.cls}`}>
                      {badge.label}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {p.coverage !== null ? (
                      <CoverageBar value={p.coverage} />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-foreground">
                    {p.zrodla !== null ? p.zrodla : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    {p.braki !== null ? (
                      <span className={`font-mono ${p.braki > 3 ? "text-amber-600" : "text-foreground"}`}>
                        {p.braki}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {p.marketplace.length > 0 ? (
                        p.marketplace.map((m) => (
                          <span key={m} className="px-1.5 py-0.5 text-[11px] bg-muted rounded text-muted-foreground">
                            {m}
                          </span>
                        ))
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => onDetail(p.id)}
                        className="px-2.5 py-1 text-[11px] font-medium border border-border rounded hover:bg-muted transition-colors text-foreground"
                      >
                        Otwórz
                      </button>
                      <button onClick={onResearch} className="px-2.5 py-1 text-[11px] font-medium text-primary bg-accent border border-accent rounded hover:bg-primary hover:text-primary-foreground transition-colors">
                        Research
                      </button>
                    </div>
                  </td>
                </tr>
              );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Package size={28} className="mb-3 opacity-30" />
            <p className="text-sm">Brak wyników dla &ldquo;{query}&rdquo;</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page: Produkt — Szczegóły ────────────────────────────────────────────────
function ProductBenchmarkPanel({ product }: { product: Product }) {
  const [data, setData] = useState<BenchmarkResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set([product.slug]));
  const [onlyDifferences, setOnlyDifferences] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void apiRequest<BenchmarkResponse>(`/products/${product.slug}/benchmark`)
      .then((response) => {
        if (!active) return;
        setData(response);
        const initial = response.models.slice(0, 5).map((model) => model.slug);
        if (initial.includes(product.slug)) setSelected(new Set(initial));
      })
      .catch((requestError) => active && setError(requestError instanceof Error ? requestError.message : "Nie udało się wczytać benchmarku kategorii."));
    return () => { active = false; };
  }, [product.slug]);

  const toggle = (slug: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(slug)) next.delete(slug);
    else if (next.size < 5) next.add(slug);
    return next.size ? next : new Set([product.slug]);
  });
  const models = (data?.models || []).filter((model) => selected.has(model.slug));
  const rows = (data?.fields || []).filter((field) => {
    if (!onlyDifferences) return true;
    const values = models.map((model) => model.values[field]?.value || "X");
    return new Set(values).size > 1;
  });

  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  if (!data) return <div className="rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">Wczytywanie benchmarku kategorii…</div>;
  if (!data.has_comparison) return <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center"><GitCompare size={24} className="mx-auto text-muted-foreground" /><p className="mt-3 text-sm font-medium text-foreground">Brak innych przeanalizowanych produktów w tej kategorii.</p><p className="mt-1 text-xs text-muted-foreground">Gdy kolejny produkt z kategorii „{data.benchmark_category || "tej"}” zostanie przeanalizowany, pojawi się tutaj porównanie.</p></div>;

  return <section className="rounded-lg border border-border bg-card p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-semibold text-foreground">Porównanie w kategorii: {data.benchmark_category}</h2><p className="mt-1 text-xs text-muted-foreground">Wybierz od 2 do 5 produktów. Ten widok porównuje modele, nie powiela karty pojedynczego produktu.</p></div><label className="inline-flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={onlyDifferences} onChange={(event) => setOnlyDifferences(event.target.checked)} />Tylko różnice</label></div><div className="mt-4 flex flex-wrap gap-2">{data.models.map((model) => <label key={model.slug} className={`inline-flex cursor-pointer items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs ${selected.has(model.slug) ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground"}`}><input className="sr-only" type="checkbox" checked={selected.has(model.slug)} onChange={() => toggle(model.slug)} /><span>{model.brand} {model.model}</span><span className="text-[10px] opacity-70">{model.coverage ?? "—"}%</span></label>)}</div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-xs"><thead><tr className="border-b border-border text-left text-muted-foreground"><th className="sticky left-0 z-10 bg-card px-2 py-2 font-medium">Parametr</th>{models.map((model) => <th key={model.slug} className="min-w-44 px-2 py-2 font-medium">{model.brand} {model.model}</th>)}</tr></thead><tbody>{rows.map((field) => <tr key={field} className="border-b border-border last:border-0 align-top"><td className="sticky left-0 z-10 bg-card px-2 py-2.5 font-medium text-foreground">{field}</td>{models.map((model) => { const value = model.values[field]?.value || "X"; const different = models.some((other) => (other.values[field]?.value || "X") !== value); return <td key={model.slug} className={`px-2 py-2.5 ${different ? "bg-amber-50/50" : ""} ${value === "X" ? "text-muted-foreground" : "text-foreground"}`}>{value === "X" ? "Brak danych" : value}</td>; })}</tr>)}</tbody></table></div></section>;
}

function PageProduktSzczegoly({ productId, onBack, onResearch, onSources }: { productId: string; onBack: () => void; onResearch: () => void; onSources: () => void }) {
  const p = PRODUCTS.find((x) => x.id === productId) || PRODUCTS[0];
  const badge = statusBadge(p.status);
  const details = PRODUCT_DETAILS[p.id];
  const [selectedEvidence, setSelectedEvidence] = useState<FieldEvidence | null>(null);
  const [refreshModalOpen, setRefreshModalOpen] = useState(false);
  const [refreshMode, setRefreshMode] = useState<"incremental" | "full_reanalysis">("incremental");
  const [refreshRun, setRefreshRun] = useState<ApiRun | null>(null);
  const [refreshError, setRefreshError] = useState("");
  const [history, setHistory] = useState<RefreshHistoryEntry[] | null>(null);
  const [selectedHistory, setSelectedHistory] = useState<RefreshHistoryEntry | null>(null);
  const [analysisRuns, setAnalysisRuns] = useState<ApiRun[]>([]);
  const [historySnapshot, setHistorySnapshot] = useState<HistorySnapshot | null>(null);
  const [activeTab, setActiveTab] = useState<"product" | "benchmark" | "history">("product");
  const [fieldFilter, setFieldFilter] = useState<"all" | "valid" | "weak" | "conflicting" | "missing" | "legacy">("all");
  const [analysisMode, setAnalysisMode] = useState<"saved" | "refresh">("saved");
  const fields = details?.fields || [];
  const metrics = p.metrics;
  const visibleFields = fields.filter((field) => {
    if (fieldFilter === "all") return true;
    if (fieldFilter === "missing") return field.value === "X";
    if (fieldFilter === "conflicting") return field.status === "conflicting" || Boolean(field.provenance?.has_conflict);
    if (fieldFilter === "legacy") return field.evidence.some((item) => item.evidence_status === "unattributed_legacy");
    return field.validation_status === fieldFilter;
  });
  const marketplaceSourcesCount = (details?.sources || []).filter((source) => source.marketplace !== "manufacturer").length;

  const loadHistory = async () => {
    try {
      const response = await apiRequest<{ history: ApiRun[]; runs?: ApiRun[] }>(`/products/${p.slug}/history`);
      const entries: RefreshHistoryEntry[] = (response.history || []).map((run) => ({
        version: run.run_id,
        run_id: run.run_id,
        mode: run.run_type === "refresh" ? "incremental" : run.run_type === "reanalysis" ? "analysis" : "full_reanalysis",
        started_at: run.started_at || "",
        finished_at: run.finished_at,
        sources_before: 0,
        sources_after: run.sources_attached || 0,
        new_sources: [], changed_sources: [], unavailable_sources: [],
        fields_changed: run.changed_fields || [],
        coverage_before: run.coverage_before ?? null,
        coverage_after: run.coverage_after ?? null,
      }));
      setHistory(entries);
      setSelectedHistory(entries[0] || null);
      setAnalysisRuns(response.runs || []);
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Nie udało się wczytać historii odświeżeń.");
    }
  };

  const startRefresh = async () => {
    setRefreshError("");
    try {
      const created = await apiRequest<ApiRun>(`/products/${p.slug}/refresh`, {
        method: "POST",
        body: JSON.stringify({ mode: refreshMode }),
      });
      setRefreshRun(created);
      setRefreshModalOpen(false);
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Nie udało się uruchomić odświeżania.");
    }
  };

  const startAnalysis = async () => {
    setRefreshError("");
    try {
      const created = await apiRequest<ApiRun>(`/products/${p.slug}/analyze`, {
        method: "POST",
        body: JSON.stringify({ refresh_sources: analysisMode === "refresh" }),
      });
      setRefreshRun(created);
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Nie udało się uruchomić analizy.");
    }
  };

  const openHistorySnapshot = async (entry: RefreshHistoryEntry) => {
    try {
      setHistorySnapshot(await apiRequest<HistorySnapshot>(`/products/${p.slug}/history/${entry.version}/snapshot`));
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Nie udało się otworzyć snapshotu wyniku.");
    }
  };

  useEffect(() => {
    if (!refreshRun || !["queued", "running"].includes(refreshRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await apiRequest<ApiRun>(`/runs/${refreshRun.run_id}`);
        setRefreshRun(latest);
        if (!["queued", "running"].includes(latest.status)) void loadHistory();
      } catch (error) {
        setRefreshError(error instanceof Error ? error.message : "Utracono połączenie z lokalnym API.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refreshRun?.run_id, refreshRun?.status]);

  const fieldStatus = (field: ProductField) => {
    if (field.status === "confirmed") return { label: "Potwierdzone", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" };
    if (field.status === "conflicting") return { label: "Konflikt", cls: "bg-amber-50 text-amber-700 border-amber-200" };
    if (field.value === "X") return { label: "Brak danych", cls: "bg-muted text-muted-foreground border-border" };
    return { label: "Otwarte", cls: "bg-muted text-muted-foreground border-border" };
  };

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
          <button onClick={onBack} className="hover:text-foreground transition-colors flex items-center gap-1">
            <ArrowLeft size={11} />
            Produkty
          </button>
          <ChevronRight size={11} />
          <span className="text-foreground font-medium">{p.name}</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-base font-semibold text-foreground">{p.brand} {p.name}</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Model wózka spacerowego</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-medium ${badge.cls}`}>{badge.label}</span>
            <button onClick={() => setRefreshModalOpen(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded hover:bg-muted transition-colors">
              <RefreshCw size={13} />
              Odśwież dane
            </button>
            <button onClick={onSources} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded hover:bg-muted transition-colors">
              <Layers size={13} />
              Aukcje ({marketplaceSourcesCount})
            </button>
            <button onClick={onResearch} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors"><Plus size={13} />Nowy research</button>
          </div>
        </div>
        <div className="mt-4 flex gap-1 overflow-x-auto border-b border-border -mb-4" role="tablist" aria-label="Sekcje produktu">
          <button role="tab" aria-selected={activeTab === "product"} onClick={() => setActiveTab("product")} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "product" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Dane produktu</button>
          <button role="tab" aria-selected={activeTab === "benchmark"} onClick={() => setActiveTab("benchmark")} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "benchmark" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Benchmark</button>
          <button role="tab" aria-selected={false} onClick={onSources} className="px-3 py-2 text-xs font-medium border-b-2 border-transparent text-muted-foreground hover:text-foreground transition-colors">Aukcje i źródła</button>
          <button role="tab" aria-selected={activeTab === "history"} onClick={() => { setActiveTab("history"); void loadHistory(); }} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "history" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Historia</button>
        </div>
      </div>

      {activeTab === "history" ? <div className="flex-1 overflow-auto px-6 py-5 space-y-4"><section className="max-w-3xl bg-card border border-border rounded-lg p-4"><div className="flex items-center justify-between gap-2"><h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Clock size={14} className="text-muted-foreground" />Historia produktu</h2><button onClick={() => void loadHistory()} className="text-xs text-primary hover:underline">Odśwież listę</button></div>{analysisRuns.length > 0 && <div className="mt-4"><p className="text-xs font-medium text-foreground">Uruchomienia analizy</p><div className="mt-2 space-y-2">{analysisRuns.map((run) => <div key={run.run_id} className="rounded border border-border bg-muted/20 p-3 text-xs"><p className="font-medium text-foreground">{["success", "succeeded"].includes(run.status) ? "Analiza zakończona" : ["failed", "timed_out", "cancelled", "interrupted"].includes(run.status) ? "Analiza zatrzymana" : "Analiza w toku"}</p><p className="mt-1 text-muted-foreground">{run.started_at ? new Date(run.started_at).toLocaleString("pl-PL") : "—"} · użyte źródła: {run.analysis?.used_sources?.length ?? 0}</p><p className="mt-1 text-muted-foreground">Coverage: {run.analysis?.coverage_before ?? "—"}% → {run.analysis?.coverage_after ?? "—"}% · zmienione pola: {run.analysis?.fields_changed ?? 0}</p>{run.error && <p className="mt-2 text-red-700">{run.error}</p>}</div>)}</div></div>}{DEVELOPER_MODE && <details className="mt-4 rounded border border-border bg-muted/20 p-3 text-xs"><summary className="cursor-pointer font-medium text-foreground">Narzędzia developerskie</summary><p className="mt-2 text-muted-foreground">Ta akcja ponownie analizuje wyłącznie zapisane dane. Nie uruchamia wyszukiwania ofert.</p><button onClick={() => { setAnalysisMode("saved"); void startAnalysis(); }} className="mt-3 rounded border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted">Przeanalizuj ponownie zapisane dane</button></details>}{history === null ? <p className="mt-3 text-xs text-muted-foreground">Wczytywanie wersji zapisanych przed odświeżeniami.</p> : history.length === 0 ? <p className="mt-3 text-xs text-muted-foreground">Brak zapisanych wersji dla tego produktu.</p> : <div className="mt-4 space-y-2">{history.map((entry) => <button key={entry.version} onClick={() => { setSelectedHistory(entry); setHistorySnapshot(null); }} className={`w-full rounded border p-3 text-left text-xs transition-colors ${selectedHistory?.version === entry.version ? "border-primary bg-accent" : "border-border hover:bg-muted/40"}`}><p className="font-medium text-foreground">{entry.mode === "incremental" ? "Odświeżenie przyrostowe" : entry.mode === "analysis" ? "Analiza zapisanych danych" : "Pełna ponowna analiza"}</p><p className="mt-1 text-muted-foreground">{entry.started_at ? new Date(entry.started_at).toLocaleString("pl-PL") : entry.version}</p><p className="mt-1 text-muted-foreground">Coverage: {entry.coverage_before ?? "—"}% → {entry.coverage_after ?? "—"}% · zmienione pola: {entry.fields_changed.length}</p></button>)}</div>}{selectedHistory && <div className="mt-4 rounded border border-border bg-muted/20 p-3 text-xs text-muted-foreground"><p className="font-medium text-foreground">Szczegóły wersji</p><p className="mt-1">Nowe źródła: {selectedHistory.new_sources.length}; niedostępne: {selectedHistory.unavailable_sources.length}</p><p>Zmodyfikowane pola: {selectedHistory.fields_changed.length ? selectedHistory.fields_changed.join(", ") : "brak"}</p><button onClick={() => void openHistorySnapshot(selectedHistory)} className="mt-3 text-primary hover:underline">Otwórz snapshot wyniku</button>{historySnapshot && <div className="mt-3 rounded border border-border bg-card p-2"><p className="font-medium text-foreground">Pola w zapisanej wersji: {historySnapshot.fields.length}</p><p className="mt-1">Potwierdzone: {historySnapshot.fields.filter((field) => field.value !== "X").length}; braki: {historySnapshot.fields.filter((field) => field.value === "X").length}</p></div>}</div>}</section></div> : activeTab === "benchmark" ? <div className="flex-1 overflow-auto px-6 py-5"><ProductBenchmarkPanel product={p} /></div> : (
      <div className="flex-1 px-6 py-5 grid grid-cols-3 gap-5 min-h-0">
        <div className="col-span-2 flex flex-col gap-4">
          <section className="bg-card border border-border rounded-lg p-4">
            <h2 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5">
              <BarChart2 size={13} className="text-muted-foreground" />
              Stan benchmarku
            </h2>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <div className="p-3 bg-muted/30 rounded border border-border"><div className="text-[11px] text-muted-foreground mb-1">Pola z wartością</div><div className="text-sm font-semibold font-mono text-foreground">{metrics?.analysis_complete ? `${metrics.fields_present} / ${metrics.fields_total}` : "Nie przeanalizowano"}</div></div>
              <div className="p-3 bg-muted/30 rounded border border-border"><div className="text-[11px] text-muted-foreground mb-1">Jakość dowodów</div><div className="text-sm font-semibold font-mono text-foreground">{metrics?.evidence_quality_percent ?? "—"}{metrics?.evidence_quality_percent !== null && metrics?.evidence_quality_percent !== undefined ? "%" : ""}</div></div>
              <div className="p-3 bg-muted/30 rounded border border-border"><div className="text-[11px] text-muted-foreground mb-1">Braki danych</div><div className="text-sm font-semibold font-mono text-foreground">{metrics?.analysis_complete ? metrics.missing_fields : "Nie przeanalizowano"}</div></div>
              <div className="p-3 bg-muted/30 rounded border border-border"><div className="text-[11px] text-muted-foreground mb-1">Konflikty</div><div className="text-sm font-semibold font-mono text-foreground">{metrics?.conflicting_fields ?? p.conflicts}</div></div>
            </div>
            {p.coverage !== null && <div className="mt-4"><div className="flex items-center justify-between mb-1.5"><span className="text-[11px] text-muted-foreground">Coverage danych (nie jest oceną jakości)</span><span className="text-xs font-mono font-medium text-foreground">{p.coverage}%</span></div><div className="h-2 bg-muted rounded-full overflow-hidden"><div className={`h-full rounded-full ${p.coverage >= 65 ? "bg-emerald-500" : p.coverage >= 50 ? "bg-amber-400" : "bg-red-400"}`} style={{ width: `${p.coverage}%` }} /></div></div>}
          </section>

          <section className="bg-card border border-border rounded-lg p-4">
            <h2 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5"><FileText size={13} className="text-muted-foreground" />Parametry produktu</h2>
            {fields.length ? <><div className="mb-3 flex flex-wrap gap-1.5">{([['all','Wszystkie'],['valid','Potwierdzone'],['weak','Słabe'],['conflicting','Konflikty'],['missing','Braki'],['legacy','Historyczne bez źródła']] as const).map(([key,label]) => <button key={key} onClick={() => setFieldFilter(key)} className={`rounded-full border px-2 py-1 text-[11px] ${fieldFilter === key ? 'border-primary bg-accent text-primary' : 'border-border text-muted-foreground hover:bg-muted'}`}>{label}</button>)}</div><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="border-b border-border text-left text-muted-foreground"><th className="px-2 py-2 font-medium">Parametr</th><th className="px-2 py-2 font-medium">Wartość</th><th className="px-2 py-2 font-medium">Status</th><th className="px-2 py-2 font-medium">Potwierdzenia</th><th className="px-2 py-2 font-medium">Źródła</th></tr></thead><tbody>{visibleFields.map((field) => {
              const status = fieldStatus(field);
              const usableEvidence = field.evidence.filter((evidence) => Boolean(evidence.source_id && evidence.excerpt));
              return <tr key={field.field_name} className="border-b border-border last:border-0 align-top"><td className="px-2 py-2.5 font-medium text-foreground">{field.field_name}</td><td className="px-2 py-2.5 text-foreground">{field.value === "X" ? "Brak danych" : field.value}</td><td className="px-2 py-2.5"><span className={`inline-flex px-2 py-0.5 rounded border text-[11px] font-medium ${status.cls}`}>{status.label}</span></td><td className="px-2 py-2.5 text-muted-foreground">{field.provenance?.independent_confirmations_count ?? 0} niezależne / {field.provenance?.total_sources_count ?? usableEvidence.length} źródła</td><td className="px-2 py-2.5">{usableEvidence.length ? <div className="flex flex-wrap gap-1">{usableEvidence.map((evidence, index) => <button key={`${field.field_name}-${evidence.source_id}-${index}`} onClick={() => setSelectedEvidence(evidence)} title={`Domena: ${evidence.domain || "brak"}\n${evidence.excerpt}`} className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground hover:bg-accent hover:text-primary transition-colors">{evidence.domain || "Źródło"}{evidence.is_independent_confirmation ? " · niezależne" : ""}</button>)}</div> : <span className="text-muted-foreground">Brak zapisanego dowodu</span>}</td></tr>;
            })}</tbody></table></div></> : <div className="flex items-start gap-2 p-3 bg-muted/30 rounded text-xs text-muted-foreground"><Clock size={13} className="mt-0.5 flex-shrink-0" />Trwa przygotowanie danych produktu. Stan analizy jest widoczny w Historii.</div>}
          </section>
        </div>

        <div className="flex flex-col gap-4">
          <section className="bg-card border border-border rounded-lg p-4">
            <h2 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5"><Link2 size={13} className="text-muted-foreground" />Dowód źródłowy</h2>
            {selectedEvidence ? <div className="flex flex-col gap-3 text-xs"><div><p className="text-[11px] text-muted-foreground">Domena i status</p><p className="font-medium text-foreground">{selectedEvidence.domain || "Brak domeny"} <span className="font-normal text-muted-foreground">· {selectedEvidence.source_status === "active" ? "aktywne" : selectedEvidence.source_status === "unavailable" ? "niedostępne" : "niezweryfikowane"}</span></p></div><div className="grid grid-cols-2 gap-3"><div><p className="text-[11px] text-muted-foreground">Typ źródła</p><p className="text-foreground break-words">{selectedEvidence.source_type || "Brak metadanych"}</p></div><div><p className="text-[11px] text-muted-foreground">ID oferty</p><p className="font-mono text-foreground break-all">{selectedEvidence.offer_id || "—"}</p></div></div><div><p className="text-[11px] text-muted-foreground mb-1">Cytat</p><p className="p-2.5 bg-muted/30 border border-border rounded text-foreground leading-relaxed whitespace-pre-wrap">{selectedEvidence.evidence}</p></div><div className="rounded border border-border bg-muted/20 p-2.5 text-[11px] text-muted-foreground space-y-1"><p>Źródło: <span className="font-mono text-foreground break-all">{selectedEvidence.source_id}</span></p><p>Pobrano: <span className="text-foreground">{selectedEvidence.fetched_at || "—"}</span></p><p>Hash zawartości: <span className="font-mono text-foreground break-all">{selectedEvidence.content_hash || "Brak"}</span></p><p>Snapshot surowy: <span className="font-mono text-foreground break-all">{selectedEvidence.raw_snapshot_path || "Brak"}</span></p><p>Snapshot oczyszczony: <span className="font-mono text-foreground break-all">{selectedEvidence.clean_snapshot_path || "Brak"}</span></p></div>{(selectedEvidence.original_url || selectedEvidence.source_url) ? <a href={selectedEvidence.original_url || selectedEvidence.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-primary hover:underline"><ExternalLink size={12} />Otwórz aukcję / źródło</a> : <p className="text-muted-foreground">Brak zapisanego linku do źródła.</p>}</div> : <p className="text-xs text-muted-foreground">Wybierz źródło z tabeli, aby zobaczyć cytat, metadane i lokalny snapshot.</p>}
          </section>
          <section className="bg-card border border-border rounded-lg p-4"><h2 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5"><Clock size={13} className="text-muted-foreground" />Źródła użyte w danych</h2><p className="text-xs text-muted-foreground">{p.zrodla ?? 0} źródeł wykorzystanych w finalnym rekordzie</p><div className="mt-2 flex flex-wrap gap-1">{p.marketplace.map((marketplace) => <span key={marketplace} className="px-1.5 py-0.5 text-[11px] bg-muted rounded text-muted-foreground">{marketplace}</span>)}</div><p className="text-[11px] text-muted-foreground mt-3">Snapshot: {p.lastRun || "—"}</p></section>
          <section className="bg-card border border-border rounded-lg p-4"><div className="flex items-center justify-between gap-2"><h2 className="text-xs font-semibold text-foreground flex items-center gap-1.5"><Clock size={13} className="text-muted-foreground" />Historia</h2><button onClick={() => void loadHistory()} className="text-[11px] text-primary hover:underline">Odśwież listę</button></div>{history === null ? <p className="mt-2 text-xs text-muted-foreground">Wczytaj wersje zapisane przed odświeżeniami.</p> : history.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">Brak zapisanych wersji.</p> : <div className="mt-3 space-y-2">{history.map((entry) => <button key={entry.version} onClick={() => setSelectedHistory(entry)} className={`w-full rounded border p-2 text-left text-[11px] transition-colors ${selectedHistory?.version === entry.version ? "border-primary bg-accent" : "border-border hover:bg-muted/40"}`}><p className="font-medium text-foreground">{entry.mode === "incremental" ? "Odświeżenie przyrostowe" : "Pełna ponowna analiza"}</p><p className="mt-0.5 text-muted-foreground">{entry.started_at ? new Date(entry.started_at).toLocaleString("pl-PL") : entry.version}</p></button>)}</div>}{selectedHistory && <div className="mt-3 rounded border border-border bg-muted/20 p-2.5 text-[11px] text-muted-foreground"><p className="font-medium text-foreground">Porównanie wersji</p><p className="mt-1">Coverage: {selectedHistory.coverage_before ?? "—"}% → {selectedHistory.coverage_after ?? "—"}%</p><p>Zmodyfikowane pola: {selectedHistory.fields_changed.length ? selectedHistory.fields_changed.join(", ") : "brak"}</p><p>Nowe źródła: {selectedHistory.new_sources.length}; niedostępne: {selectedHistory.unavailable_sources.length}</p></div>}</section>
        </div>
      </div>
      )}
      {refreshRun && <div className={`fixed right-5 bottom-5 z-40 w-[min(420px,calc(100vw-2.5rem))] rounded-lg border bg-card p-4 shadow-lg ${["failed", "timed_out", "cancelled", "interrupted"].includes(refreshRun.status) ? "border-red-200" : ["success", "succeeded"].includes(refreshRun.status) ? "border-emerald-200" : "border-border"}`}><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold text-foreground">{refreshRun.analysis ? "Analiza zapisanych danych" : "Odświeżanie danych"}</p><span className="text-[11px] text-muted-foreground">{refreshRun.progress}%</span></div><p className="mt-1 text-xs text-muted-foreground">{refreshRun.current_step}</p>{refreshRun.logs_tail[refreshRun.logs_tail.length - 1] && <p className="mt-2 rounded bg-muted/40 p-2 text-[11px] text-muted-foreground">Ostatni log: {refreshRun.logs_tail[refreshRun.logs_tail.length - 1]}</p>}<div className="mt-3 h-1.5 overflow-hidden rounded bg-muted"><div className="h-full rounded bg-primary transition-all" style={{ width: `${refreshRun.progress}%` }} /></div>{["success", "succeeded"].includes(refreshRun.status) && <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">{refreshRun.analysis ? <><span>Użyte źródła: {refreshRun.analysis.used_sources?.length ?? 0}</span><span>Zmienione pola: {refreshRun.analysis.fields_changed ?? 0}</span><span>Coverage: {refreshRun.analysis.coverage_before ?? "—"}% → {refreshRun.analysis.coverage_after ?? "—"}%</span></> : <><span>Nowe źródła: {refreshRun.refresh?.new_sources ?? 0}</span><span>Niedostępne: {refreshRun.refresh?.unavailable_sources ?? 0}</span><span>Zmienione pola: {refreshRun.refresh?.fields_changed ?? 0}</span><span>Coverage: {refreshRun.refresh?.coverage_before ?? "—"}% → {refreshRun.refresh?.coverage_after ?? "—"}%</span></>}</div>}{["failed", "timed_out", "cancelled", "interrupted"].includes(refreshRun.status) && <><p className="mt-3 text-xs text-red-700">{refreshRun.error}</p><details className="mt-3 text-[11px] text-muted-foreground"><summary className="cursor-pointer">Dziennik techniczny</summary><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap">{refreshRun.logs_tail.join("\n")}</pre></details></>}<button onClick={() => setRefreshRun(null)} className="mt-3 text-[11px] text-primary hover:underline">Zamknij</button></div>}
      {refreshModalOpen && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"><div role="dialog" aria-modal="true" className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl"><h2 className="text-base font-semibold text-foreground">Odśwież dane: {p.brand} {p.name}</h2><p className="mt-1 text-xs text-muted-foreground">Przed każdą zmianą system zapisze wersję historyczną stanu modelu i dowodów.</p><div className="mt-4 space-y-2"><label className={`block cursor-pointer rounded-lg border p-3 ${refreshMode === "incremental" ? "border-primary bg-accent" : "border-border"}`}><input className="mr-2 accent-primary" type="radio" checked={refreshMode === "incremental"} onChange={() => setRefreshMode("incremental")} /><span className="text-xs font-medium text-foreground">Odśwież tylko nowe i zmienione źródła</span><p className="mt-1 pl-5 text-[11px] text-muted-foreground">Zalecane. Sprawdza zapisane źródła oraz lokalny listing, bez analizy niezmienionych danych.</p></label><label className={`block cursor-pointer rounded-lg border p-3 ${refreshMode === "full_reanalysis" ? "border-primary bg-accent" : "border-border"}`}><input className="mr-2 accent-primary" type="radio" checked={refreshMode === "full_reanalysis"} onChange={() => setRefreshMode("full_reanalysis")} /><span className="text-xs font-medium text-foreground">Pełna ponowna analiza</span><p className="mt-1 pl-5 text-[11px] text-muted-foreground">Ponownie analizuje wszystkie lokalne snapshoty. Wymaga lokalnego klucza OpenAI.</p></label></div>{refreshError && <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{refreshError}</p>}<div className="mt-5 flex justify-end gap-2"><button onClick={() => setRefreshModalOpen(false)} className="px-3 py-2 text-xs font-medium border border-border rounded hover:bg-muted">Anuluj</button><button onClick={() => void startRefresh()} className="px-3 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90">Uruchom odświeżanie</button></div></div></div>}
    </div>
  );
}

// ─── Page: Produkt — Aukcje i źródła ─────────────────────────────────────────
function SourceContributionPanel({ data, onClose }: { data: SourceContributionResponse; onClose: () => void }) {
  const sections: Array<[string, ContributionField[]]> = [
    ["Nowe dane", data.contribution.unique_fields_contributed],
    ["Potwierdzone dane", data.contribution.confirmed_fields],
    ["Konflikty", data.contribution.conflicting_fields],
    ["Niewykorzystane dowody", data.contribution.rejected_evidence],
  ];
  return <aside className="fixed right-0 top-0 z-50 flex h-full w-[min(560px,100vw)] flex-col border-l border-border bg-card shadow-2xl"><div className="flex items-start justify-between gap-3 border-b border-border p-4"><div><p className="text-[11px] text-muted-foreground">Wkład źródła</p><h2 className="mt-1 text-sm font-semibold text-foreground break-words">{data.title}</h2></div><button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Zamknij panel"><X size={16} /></button></div><div className="min-h-0 flex-1 overflow-auto p-4">{data.zero_contribution ? <div className="rounded border border-border bg-muted/30 p-4 text-sm text-muted-foreground">{data.message}</div> : <><div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4"><div className="rounded bg-muted/30 p-2">Nowe: <b>{data.summary.unique_fields_contributed}</b></div><div className="rounded bg-muted/30 p-2">Potwierdzenia: <b>{data.summary.confirmed_fields}</b></div><div className="rounded bg-muted/30 p-2">Konflikty: <b>{data.summary.conflicting_fields}</b></div><div className="rounded bg-muted/30 p-2">Finalnie użyte: <b>{data.summary.final_fields_used}</b></div></div>{sections.map(([title, fields]) => fields.length > 0 && <section key={title} className="mt-5"><h3 className="text-xs font-semibold text-foreground">{title}</h3><div className="mt-2 space-y-2">{fields.map((field, index) => <div key={`${field.field_name}-${index}`} className="rounded border border-border bg-muted/20 p-3"><p className="text-xs font-medium text-foreground">{field.field_name}: <span className="font-normal">{field.value}</span></p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{field.excerpt}</p></div>)}</div></section>)}</>}</div></aside>;
}

function PageProduktZrodla({ productId, onBack }: { productId: string; onBack: () => void }) {
  const product = PRODUCTS.find((item) => item.id === productId) || PRODUCTS[0];
  const [data, setData] = useState<ProductSourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | ProductSource["role"] | "unavailable">("all");
  const [selectedSource, setSelectedSource] = useState<ProductSource | null>(null);
  const [snapshot, setSnapshot] = useState<SourceSnapshotResponse | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [contribution, setContribution] = useState<SourceContributionResponse | null>(null);
  const [contributionLoading, setContributionLoading] = useState(false);

  const loadSources = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest<ProductSourcesResponse>(`/products/${product.slug}/sources`);
      setData(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Nie udało się wczytać zapisanych źródeł.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadSources(); }, [product.slug]);

  const openSnapshot = async (source: ProductSource) => {
    setSelectedSource(source);
    setSnapshot(null);
    setContribution(null);
    setSnapshotLoading(true);
    try {
      const response = await apiRequest<SourceSnapshotResponse>(`/products/${product.slug}/sources/${encodeURIComponent(source.source_id)}/snapshot`);
      setSnapshot(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Nie udało się otworzyć lokalnego snapshotu.");
    } finally {
      setSnapshotLoading(false);
    }
  };

  const openContribution = async (source: ProductSource) => {
    setSelectedSource(source);
    setSnapshot(null);
    setContribution(null);
    setContributionLoading(true);
    try {
      const response = await apiRequest<SourceContributionResponse>(`/products/${product.slug}/sources/${encodeURIComponent(source.source_id)}/contribution`);
      setContribution(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Nie udało się wczytać wkładu źródła.");
    } finally {
      setContributionLoading(false);
    }
  };

  const sourceStatus = (status: ProductSource["source_status"]) => ({
    active: { label: "URL aktywny", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    unavailable: { label: "Aukcja niedostępna", cls: "bg-red-50 text-red-700 border-red-200" },
    unchecked: { label: "URL niezweryfikowany", cls: "bg-muted text-muted-foreground border-border" },
  }[status]);
  const fetchStatus = (status: ProductSource["fetch_status"]) => ({ fetched: "Pobrano", failed: "Błąd pobrania", skipped: "Pominięto" }[status]);
  const cleanerStatus = (status: ProductSource["cleaner_status"]) => ({ cleaned: "Oczyszczono", not_cleaned: "Nie oczyszczono", unavailable: "Brak snapshotu" }[status]);
  const roleLabel = (role: ProductSource["role"]) => ({ primary: "Główne", supplementary: "Uzupełniające", manufacturer: "Oficjalne", fetched_but_unattached: "Pobrane, niewykorzystane", failed: "Nieudane pobranie", duplicate: "Duplikat treści", rejected: "Odrzucone" }[role]);
  const filtered = (data?.sources || []).filter((source) => {
    if (filter === "all") return true;
    if (filter === "unavailable") return source.source_status === "unavailable";
    return source.role === filter && source.source_status !== "unavailable";
  });
  const sections: Array<{ key: string; title: string; sources: ProductSource[] }> = [
    { key: "primary", title: "Źródła główne", sources: filtered.filter((source) => source.role === "primary") },
    { key: "supplementary", title: "Źródła uzupełniające", sources: filtered.filter((source) => source.role === "supplementary") },
    { key: "manufacturer", title: "Oficjalne źródła", sources: filtered.filter((source) => source.role === "manufacturer") },
    { key: "unattached", title: "Pobrane, ale niewykorzystane", sources: filtered.filter((source) => source.role === "fetched_but_unattached") },
    { key: "duplicate", title: "Duplikaty", sources: filtered.filter((source) => source.role === "duplicate") },
    { key: "failed", title: "Nieudane pobrania", sources: filtered.filter((source) => source.role === "failed") },
    { key: "rejected", title: "Odrzucone źródła", sources: filtered.filter((source) => source.role === "rejected") },
  ];

  const SourceCard = ({ source }: { source: ProductSource }) => {
    const status = sourceStatus(source.source_status);
    const checks = [
      ["Wybrana", source.selected],
      ["Pobrana", source.fetched],
      ["Oczyszczona", source.cleaned],
      ["Przypięta", source.attached],
      ["Użyta w benchmarku", source.used_in_benchmark],
    ];
    const contributionSummary = source.contribution;
    return <article className="rounded-lg border border-border bg-card p-4 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-1.5"><span className="text-[11px] font-medium text-primary">{roleLabel(source.role)}</span><span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${status.cls}`}>{status.label}</span></div><h3 className="mt-1.5 text-sm font-semibold text-foreground break-words">{source.title}</h3><p className="mt-1 text-[11px] text-muted-foreground">{source.marketplace === "manufacturer" ? "Oficjalne źródło producenta" : "Aukcja marketplace"} · {source.domain || "brak domeny"}</p></div><div className="flex flex-wrap gap-2"><button onClick={() => void openContribution(source)} className="rounded border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted">Pokaż wkład źródła</button>{source.snapshot_available ? <button onClick={() => void openSnapshot(source)} className="rounded border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted">Otwórz snapshot</button> : <span className="rounded border border-border px-2.5 py-1.5 text-[11px] text-muted-foreground">Brak snapshotu</span>}{source.original_url ? <a href={source.original_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded bg-primary px-2.5 py-1.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"><ExternalLink size={12} />Otwórz aukcję</a> : <span className="rounded bg-muted px-2.5 py-1.5 text-[11px] text-muted-foreground">Brak URL</span>}</div></div><div className="mt-3 flex flex-wrap gap-1.5">{checks.map(([label, complete]) => <span key={String(label)} className={`rounded border px-1.5 py-0.5 text-[10px] ${complete ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-border bg-muted text-muted-foreground"}`}>{complete ? "✓" : "—"} {label}</span>)}</div><div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4"><div className="rounded bg-muted/30 p-2">Nowe pola: <b>{contributionSummary?.unique_fields_contributed.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Potwierdzenia: <b>{contributionSummary?.confirmed_fields.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Konflikty: <b>{contributionSummary?.conflicting_fields.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Finalnie użyte: <b>{contributionSummary?.final_fields_used.length ?? 0}</b></div></div><div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[11px] sm:grid-cols-3 xl:grid-cols-5"><div><p className="text-muted-foreground">ID oferty</p><p className="mt-0.5 font-mono text-foreground break-all">{source.offer_id || "—"}</p></div><div><p className="text-muted-foreground">Cena</p><p className="mt-0.5 text-foreground">{source.price || "—"}</p></div><div><p className="text-muted-foreground">Sprzedawca</p><p className="mt-0.5 text-foreground break-words">{source.seller.name || "—"}{source.seller.rating ? ` · ${source.seller.rating}` : ""}</p></div><div><p className="text-muted-foreground">Stan pobrania</p><p className="mt-0.5 text-foreground">{fetchStatus(source.fetch_status)} · {cleanerStatus(source.cleaner_status)}</p></div><div><p className="text-muted-foreground">Wartość źródła</p><p className="mt-0.5 text-foreground">{source.offer_quality.score ?? "—"}{source.offer_quality.score !== null ? "/100" : ""}</p></div></div>{source.fetch_error && <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-[11px] text-red-700">Błąd pobrania: {source.fetch_error}</p>}<div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground"><span>Źródło: <span className="font-mono text-foreground">{source.source_id}</span></span><span>Pierwsze pobranie: {source.first_fetched_at ? new Date(source.first_fetched_at).toLocaleString("pl-PL") : "—"}</span><span>Ostatnie pobranie: {source.last_fetched_at ? new Date(source.last_fetched_at).toLocaleString("pl-PL") : "—"}</span></div></article>;
  };

  return <div className="h-full overflow-auto"><div className="border-b border-border bg-card px-6 py-4"><div className="flex items-center gap-1.5 text-xs text-muted-foreground"><button onClick={onBack} className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft size={11} />{product.brand} {product.name}</button><ChevronRight size={11} /><span className="font-medium text-foreground">Aukcje i źródła</span></div><div className="mt-3 flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-base font-semibold text-foreground">Aukcje i źródła: {product.brand} {product.name}</h1><p className="mt-1 text-xs text-muted-foreground">Każda wybrana oferta jest rozliczona niezależnie od powodzenia pobrania i przypięcia do benchmarku.</p></div><button onClick={() => void loadSources()} className="inline-flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"><RefreshCw size={13} />Odśwież widok</button></div><div className="mt-4 flex gap-1 overflow-x-auto" role="tablist" aria-label="Sekcje produktu"><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Dane produktu</button><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Benchmark</button><span className="border-b-2 border-primary px-3 py-2 text-xs font-medium text-primary">Aukcje i źródła</span><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Historia</button></div></div><main className="px-6 py-5"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Wybrane", data?.selected_count ?? 0], ["Pobrane", data?.fetched_count ?? 0], ["Błędy pobrania", data?.failed_count ?? 0], ["Przypięte", data?.attached_count ?? 0], ["Niewykorzystane", data?.unattached_count ?? 0]].map(([label, count]) => <div key={String(label)} className="rounded-lg border border-border bg-card p-3"><p className="text-[11px] text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold text-foreground">{count}</p></div>)}</div><div className="mt-3 flex flex-wrap gap-2">{[["Wszystkie", "all"], ["Główne", "primary"], ["Uzupełniające", "supplementary"], ["Oficjalne", "manufacturer"], ["Niewykorzystane", "fetched_but_unattached"], ["Nieudane", "failed"], ["Duplikaty", "duplicate"], ["Odrzucone", "rejected"]].map(([label, key]) => <button key={String(key)} onClick={() => setFilter(key as typeof filter)} className={`rounded-full border px-3 py-1 text-[11px] ${filter === key ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground hover:bg-muted"}`}>{label}</button>)}</div>{loading ? <div className="mt-6 rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">Wczytywanie źródeł produktu…</div> : error ? <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : data?.total === 0 ? <div className="mt-6 rounded-lg border border-dashed border-border bg-card p-10 text-center"><Layers size={28} className="mx-auto text-muted-foreground opacity-50" /><p className="mt-3 text-sm font-medium text-foreground">Ten produkt nie ma jeszcze zapisanych aukcji.</p><p className="mt-1 text-xs text-muted-foreground">Uruchom research, aby przypisać źródła do produktu.</p></div> : <div className="mt-6 space-y-7">{sections.map((section) => section.sources.length > 0 && <section key={section.key}><div className="mb-3 flex items-center gap-2"><h2 className="text-sm font-semibold text-foreground">{section.title}</h2><span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{section.sources.length}</span></div><div className="space-y-3">{section.sources.map((source) => <SourceCard key={source.source_id} source={source} />)}</div></section>)}</div>}</main>{contribution && <SourceContributionPanel data={contribution} onClose={() => { setContribution(null); setSelectedSource(null); }} />}{selectedSource && !contribution && <aside className="fixed right-0 top-0 z-50 flex h-full w-[min(560px,100vw)] flex-col border-l border-border bg-card shadow-2xl"><div className="flex items-start justify-between gap-3 border-b border-border p-4"><div className="min-w-0"><p className="text-[11px] text-muted-foreground">{snapshot ? "Lokalny snapshot" : "Użyte dane źródła"}</p><h2 className="mt-1 text-sm font-semibold text-foreground break-words">{selectedSource.title}</h2></div><button onClick={() => { setSelectedSource(null); setSnapshot(null); }} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Zamknij panel"><X size={16} /></button></div>{snapshotLoading ? <p className="p-5 text-sm text-muted-foreground">Otwieranie zapisanego snapshotu…</p> : snapshot ? <div className="min-h-0 flex-1 overflow-auto p-4"><p className="mb-3 text-[11px] text-muted-foreground">{snapshot.snapshot_path}</p><pre className="whitespace-pre-wrap break-words rounded border border-border bg-muted/30 p-3 text-xs leading-relaxed text-foreground">{snapshot.content}</pre></div> : <div className="min-h-0 flex-1 overflow-auto p-4"><div className="grid grid-cols-2 gap-3 text-xs"><div><p className="text-muted-foreground">Źródło</p><p className="mt-1 font-mono text-foreground break-all">{selectedSource.source_id}</p></div><div><p className="text-muted-foreground">Domena</p><p className="mt-1 text-foreground">{selectedSource.domain || "—"}</p></div></div><h3 className="mt-5 text-xs font-semibold text-foreground">Pola oparte o to źródło</h3>{selectedSource.used_fields.length ? <div className="mt-2 space-y-2">{selectedSource.used_fields.map((field, index) => <div key={`${field.field_name}-${index}`} className="rounded border border-border bg-muted/20 p-3"><p className="text-xs font-medium text-foreground">{field.field_name}: <span className="font-normal">{field.value}</span></p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{field.excerpt}</p></div>)}</div> : <p className="mt-2 text-xs text-muted-foreground">To źródło nie ma zapisanego evidence przypisanego do pól produktu.</p>}<div className="mt-5 rounded border border-border bg-muted/20 p-3 text-[11px] text-muted-foreground"><p>Snapshot surowy: <span className="font-mono text-foreground break-all">{selectedSource.raw_snapshot_path || "Brak"}</span></p><p className="mt-1">Snapshot oczyszczony: <span className="font-mono text-foreground break-all">{selectedSource.clean_snapshot_path || "Brak"}</span></p></div></div>}</aside>}</div>;
}

// ─── Page: Research Wizard ────────────────────────────────────────────────────
const WIZARD_STEPS = ["Produkt", "Źródła", "Potwierdzenie", "Analiza", "Wynik"];

function PageResearch({ previousProductSlug = "" }: { previousProductSlug?: string }) {
  const [step, setStep] = useState(0);
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [selectedOfferIds, setSelectedOfferIds] = useState<Set<string>>(new Set());
  const [selectedManufacturerSourceIds, setSelectedManufacturerSourceIds] = useState<Set<string>>(new Set());
  const [previewLoading, setPreviewLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [run, setRun] = useState<ApiRun | null>(null);
  const runFailed = ["failed", "timed_out", "cancelled", "interrupted"].includes(run?.status || "");
  const runPartial = run?.pipeline_status === "partial" || run?.status === "partial";
  const [requestError, setRequestError] = useState("");
  const activePreviewKeyRef = useRef("");
  const previousPreviewSlugRef = useRef(previousProductSlug);

  const acceptedOffers = preview?.offers.filter((offer) => offer.match_status === "exact_match") || [];
  const previewOffers = preview?.offers || [];
  const primaryOffers = previewOffers.filter((offer) => offer.source_group === "primary_source");
  const supplementaryOffers = previewOffers.filter((offer) => offer.source_group === "supplementary_source");
  const accessoryOffers = previewOffers.filter((offer) => offer.product_type === "accessory");
  const otherOffers = previewOffers.filter((offer) => !offer.source_group && offer.product_type !== "accessory");
  const manufacturerSources = preview?.manufacturer_sources || [];
  const selectedSourcesCount = selectedOfferIds.size + selectedManufacturerSourceIds.size;
  const includeManufacturerSources = selectedManufacturerSourceIds.size > 0;
  const showSellerColumn = previewOffers.some((offer) => Boolean(offer.seller_name || offer.seller_type || offer.seller_rating !== null || offer.seller_reviews_count !== null));
  const showPriceColumn = previewOffers.some((offer) => Boolean(offer.price));
  const showConditionColumn = previewOffers.some((offer) => Boolean(offer.condition));
  const summary = preview?.summary || {};
  const comparable = (value: string) => value.trim().toLocaleLowerCase("pl-PL");
  const previewKey = (nextBrand: string, nextModel: string) => {
    const slugPart = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l").replace(/Ł/g, "l").toLocaleLowerCase("pl-PL").trim().replace(/\s+/g, "-");
    return `allegro|${slugPart(nextBrand)}|${slugPart(nextModel)}`;
  };
  const catalogBrands = [...new Set(PRODUCTS.map((product) => product.brand).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pl"));
  const modelsForBrand = [...new Set(
    PRODUCTS.filter((product) => comparable(product.brand) === comparable(brand)).map((product) => product.name),
  )].sort((a, b) => a.localeCompare(b, "pl"));
  const existingProduct = PRODUCTS.find(
    (product) => comparable(product.brand) === comparable(brand) && comparable(product.name) === comparable(model),
  );
  const trimInput = (value: string, setValue: (next: string) => void) => setValue(value.trim());

  const clearProductResearchState = () => {
    if (preview?.preview_diagnostics.current_product_slug) {
      previousPreviewSlugRef.current = preview.preview_diagnostics.current_product_slug;
    } else if (run?.product_slug) {
      previousPreviewSlugRef.current = run.product_slug;
    }
    activePreviewKeyRef.current = "";
    setPreview(null);
    setSelectedOfferIds(new Set());
    setSelectedManufacturerSourceIds(new Set());
    setRun(null);
    setRequestError("");
    setStep(0);
  };

  const updateBrand = (value: string) => {
    if (value !== brand) clearProductResearchState();
    setBrand(value);
  };

  const updateModel = (value: string) => {
    if (value !== model) clearProductResearchState();
    setModel(value);
  };

  const checkOffers = async () => {
    if (!brand.trim() || !model.trim()) {
      setRequestError("Wpisz markę i model produktu.");
      return;
    }
    const submittedBrand = brand.trim();
    const submittedModel = model.trim();
    const expectedKey = previewKey(submittedBrand, submittedModel);
    activePreviewKeyRef.current = expectedKey;
    setPreview(null);
    setSelectedOfferIds(new Set());
    setSelectedManufacturerSourceIds(new Set());
    setPreviewLoading(true);
    setRequestError("");
    try {
      const result = await apiRequest<PreviewResponse>("/research/preview", {
        method: "POST",
        body: JSON.stringify({ brand: submittedBrand, model: submittedModel, marketplace: "allegro", previous_product_slug: previousPreviewSlugRef.current }),
      });
      const responseKey = previewKey(result.requested_brand, result.requested_model);
      if (
        comparable(result.requested_brand) !== comparable(submittedBrand)
        || comparable(result.requested_model) !== comparable(submittedModel)
        || result.preview_cache_key !== expectedKey
        || responseKey !== expectedKey
        || activePreviewKeyRef.current !== expectedKey
      ) {
        throw new Error("Otrzymano wynik dla innego produktu.");
      }
      console.info("FIELDNOTE preview", result.preview_diagnostics);
      setPreview(result);
      setSelectedOfferIds(new Set(result.offers.filter((offer) => offer.source_group === "primary_source").map((offer) => offer.offer_id)));
      setSelectedManufacturerSourceIds(new Set(result.manufacturer_sources.filter((source) => source.model_match && source.match_status === "matched").map((source) => source.source_id)));
      setStep(1);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Nie udało się sprawdzić ofert.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const toggleOffer = (offerId: string) => {
    setSelectedOfferIds((previous) => {
      const next = new Set(previous);
      if (next.has(offerId)) next.delete(offerId);
      else next.add(offerId);
      return next;
    });
  };

  const toggleManufacturerSource = (sourceId: string) => {
    setSelectedManufacturerSourceIds((previous) => {
      const next = new Set(previous);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  };

  const startRun = async () => {
    if (runLoading || selectedSourcesCount === 0) return;
    setRunLoading(true);
    setRequestError("");
    try {
      const created = await apiRequest<ApiRun>("/research/run", {
        method: "POST",
        body: JSON.stringify({
          brand: brand.trim(),
          model: model.trim(),
          selected_offer_ids: [...selectedOfferIds],
          include_manufacturer_sources: includeManufacturerSources,
        }),
      });
      setRun(created);
      setStep(3);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Nie udało się uruchomić researchu.");
    } finally {
      setRunLoading(false);
    }
  };

  const retryRun = async () => {
    if (!run) return;
    setRunLoading(true);
    setRequestError("");
    try {
      const created = await apiRequest<ApiRun>(`/runs/${run.run_id}/retry`, { method: "POST" });
      setRun(created);
      setStep(3);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Nie udało się ponowić procesu.");
    } finally {
      setRunLoading(false);
    }
  };

  const refreshExistingProduct = async () => {
    if (!existingProduct) return;
    setRunLoading(true);
    setRequestError("");
    try {
      const created = await apiRequest<ApiRun>(`/products/${existingProduct.slug}/refresh`, {
        method: "POST",
        body: JSON.stringify({ mode: "incremental" }),
      });
      setRun(created);
      setStep(3);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Nie udało się odświeżyć danych produktu.");
    } finally {
      setRunLoading(false);
    }
  };

  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await apiRequest<ApiRun>(`/runs/${run.run_id}`);
        setRun(latest);
        if (!["queued", "running"].includes(latest.status)) setStep(4);
      } catch (error) {
        setRequestError(error instanceof Error ? error.message : "Utracono połączenie z lokalnym API.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);

  const reset = () => {
    setStep(0);
    clearProductResearchState();
    setBrand("");
    setModel("");
  };

  const renderOfferTable = (offers: PreviewOffer[], emptyMessage: string, allowSelection: boolean) => {
    if (!offers.length) return <p className="mt-3 text-xs text-muted-foreground">{emptyMessage}</p>;
    return <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="bg-muted/50 text-muted-foreground"><tr><th className="p-3">Wybór</th><th className="p-3">Oferta</th>{showSellerColumn && <th className="p-3">Sprzedawca</th>}{showPriceColumn && <th className="p-3">Cena</th>}{showConditionColumn && <th className="p-3">Stan</th>}<th className="p-3">Typ</th><th className="p-3">Wartość źródła</th><th className="p-3">Dopasowanie</th></tr></thead><tbody className="divide-y divide-border">{offers.map((offer) => {
      const selectable = allowSelection && offer.match_status === "exact_match" && offer.product_type === "stroller";
      const statusLabel = offer.match_status === "exact_match" ? "Dokładne" : offer.match_status === "uncertain" ? "Niepewne" : "Odrzucone";
      const statusClass = offer.match_status === "exact_match" ? "bg-emerald-50 text-emerald-700" : offer.match_status === "uncertain" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
      const typeLabel = offer.product_type === "stroller" ? "Wózek" : offer.product_type === "accessory" ? "Akcesorium" : "Nieustalony";
      const quality = offer.offer_quality;
      const qualityLabel = quality.level === "high" ? "Wysoka" : quality.level === "medium" ? "Średnia" : "Niska";
      const qualityClass = quality.level === "high" ? "bg-emerald-50 text-emerald-700" : quality.level === "medium" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
      const sellerDetails = [offer.seller_name, offer.seller_type, offer.seller_rating !== null ? `${offer.seller_rating}%` : "", offer.seller_reviews_count !== null ? `${offer.seller_reviews_count} opinii` : ""].filter(Boolean).join(" · ");
      return <tr key={offer.offer_id} className={offer.match_status === "rejected" ? "opacity-60" : ""}><td className="p-3"><input type="checkbox" disabled={!selectable} checked={selectedOfferIds.has(offer.offer_id)} onChange={() => toggleOffer(offer.offer_id)} className="accent-primary disabled:opacity-30" /></td><td className="p-3"><a href={offer.url} target="_blank" rel="noreferrer" className="font-medium text-foreground hover:underline">{offer.title || offer.offer_id}</a><p className="mt-1 flex flex-wrap gap-1 font-mono text-[10px] text-muted-foreground"><span>{offer.offer_id}</span>{offer.sponsored && <span className="rounded bg-muted px-1.5 py-0.5 font-sans">Sponsorowana</span>}</p></td>{showSellerColumn && <td className="p-3 text-muted-foreground">{sellerDetails}</td>}{showPriceColumn && <td className="p-3 text-foreground">{offer.price || ""}</td>}{showConditionColumn && <td className="p-3 text-muted-foreground">{offer.condition || ""}</td>}<td className="p-3 text-muted-foreground">{typeLabel}</td><td className="p-3"><span title={quality.reasons.join("\n")} className={`inline-flex cursor-help rounded px-2 py-1 text-[11px] ${qualityClass}`}>{quality.score}/100 · {qualityLabel}</span></td><td className="p-3"><span className={`rounded px-2 py-1 text-[11px] ${statusClass}`}>{statusLabel}</span></td></tr>;
    })}</tbody></table></div>;
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
        <h1 className="text-base font-semibold text-foreground">Nowy research</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Kreator analizy benchmarkowej</p>
      </div>

      {/* Stepper */}
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
        <div className="flex items-center gap-0">
          {WIZARD_STEPS.map((s, i) => (
            <div key={s} className="flex items-center">
              <div className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold transition-colors ${
                    i < step
                      ? "bg-emerald-500 text-white"
                      : i === step
                      ? "bg-primary text-white"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {i < step ? <CheckCircle2 size={13} /> : i + 1}
                </div>
                <span
                  className={`text-xs font-medium ${
                    i === step ? "text-foreground" : i < step ? "text-emerald-600" : "text-muted-foreground"
                  }`}
                >
                  {s}
                </span>
              </div>
              {i < WIZARD_STEPS.length - 1 && (
                <div className={`h-px w-8 mx-2 ${i < step ? "bg-emerald-300" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Step content */}
      <div className="flex-1 overflow-auto px-6 py-6">
        {/* Step 0: Produkt */}
        {step === 0 && (
          <div className="max-w-lg">
            <h2 className="text-sm font-semibold text-foreground mb-1">Wybierz produkt</h2>
            <p className="text-xs text-muted-foreground mb-4">Wpisz markę i model. Znajdziemy oficjalne źródła producenta oraz pasujące oferty Allegro.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs text-muted-foreground">Marka
                <input list="fieldnote-brands" value={brand} onChange={(event) => updateBrand(event.target.value)} onBlur={(event) => trimInput(event.target.value, updateBrand)} placeholder="np. Kinderkraft" autoComplete="off" className="mt-1 w-full rounded border border-border bg-card px-3 py-2 text-sm text-foreground" />
                <datalist id="fieldnote-brands">{catalogBrands.map((catalogBrand) => <option key={catalogBrand} value={catalogBrand} />)}</datalist>
              </label>
              <label className="text-xs text-muted-foreground">Model
                <input list="fieldnote-models" value={model} onChange={(event) => updateModel(event.target.value)} onBlur={(event) => trimInput(event.target.value, updateModel)} placeholder="np. NEBO" autoComplete="off" className="mt-1 w-full rounded border border-border bg-card px-3 py-2 text-sm text-foreground" />
                <datalist id="fieldnote-models">{modelsForBrand.map((catalogModel) => <option key={catalogModel} value={catalogModel} />)}</datalist>
              </label>
            </div>
            {existingProduct && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-medium text-amber-800">Ten produkt jest już w katalogu.</p><p className="mt-1 text-[11px] text-amber-700">Możesz bezpiecznie sprawdzić aktualne źródła, ale nie utworzymy drugiego researchu.</p><div className="mt-3 flex gap-2 flex-wrap"><button onClick={() => { window.location.assign(`/products/${existingProduct.slug}`); }} className="px-3 py-1.5 text-xs font-medium border border-amber-300 rounded text-amber-900 hover:bg-amber-100">Otwórz produkt</button><button onClick={() => void refreshExistingProduct()} disabled={runLoading} className="px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50">Odśwież dane</button><button onClick={checkOffers} disabled={previewLoading} className="px-3 py-1.5 text-xs font-medium border border-amber-300 rounded text-amber-900 hover:bg-amber-100 disabled:opacity-50">Zobacz źródła</button></div></div>}
            {requestError && <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{requestError}</p>}
            {!existingProduct && <div className="mt-6">
              <button
                onClick={checkOffers}
                disabled={previewLoading || !brand.trim() || !model.trim()}
                className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {previewLoading ? "Wyszukiwanie źródeł…" : "Znajdź źródła"}
              </button>
            </div>}
          </div>
        )}

        {/* Step 1: Oferty */}
        {step === 1 && (
          <div className="max-w-4xl">
            <h2 className="text-sm font-semibold text-foreground mb-1">Źródła dla {brand.trim()} {model.trim()}</h2>
            <p className="text-xs text-muted-foreground mb-4">Wybór w tym kroku jest tylko podglądem. Nie zapisujemy jeszcze żadnych zmian.</p>

            <section className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold text-foreground">Oficjalne źródła</h3><span className="text-[11px] text-muted-foreground">{manufacturerSources.length} znaleziono</span></div>
              {manufacturerSources.length ? <div className="mt-3 divide-y divide-border">{manufacturerSources.map((source) => {
                const selectable = source.match_status === "matched" || source.match_status === "uncertain";
                const statusLabel = source.match_status === "matched" ? "Dopasowane" : source.match_status === "uncertain" ? "Niepewne" : source.match_status === "unavailable" ? "Niedostępne" : "Odrzucone";
                const statusClass = source.match_status === "matched" ? "bg-emerald-50 text-emerald-700" : source.match_status === "uncertain" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
                return <div key={source.source_id} className="flex gap-3 py-3"><input type="checkbox" disabled={!selectable} checked={selectedManufacturerSourceIds.has(source.source_id)} onChange={() => toggleManufacturerSource(source.source_id)} className="mt-0.5 accent-primary disabled:opacity-30" /><div className="min-w-0 flex-1"><p className="text-xs font-medium text-foreground">{source.title}</p><p className="mt-1 text-[11px] text-muted-foreground">{source.type_label} · {source.domain || "brak domeny"}</p>{source.url && <a href={source.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"><ExternalLink size={10} />Otwórz źródło</a>}</div><span className={`h-fit rounded px-2 py-1 text-[11px] ${statusClass}`}>{statusLabel}</span></div>;
              })}</div> : <p className="mt-3 text-xs text-muted-foreground">Brak zapisanych oficjalnych źródeł dla tego modelu.</p>}
            </section>

            <section className="mt-4 rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold text-foreground">Oferty Allegro</h3><div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground"><span className="rounded bg-muted px-2 py-1">Znaleziono: {String(summary.unique_offer_ids ?? previewOffers.length)}</span><span className="rounded bg-emerald-50 px-2 py-1 text-emerald-700">Wózki dokładnie dopasowane: {acceptedOffers.length}</span></div></div>
              <div className="mt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Top 10 źródeł do analizy</h4><span className="text-[11px] text-muted-foreground">{primaryOffers.length}/10</span></div><p className="mt-1 text-[11px] text-muted-foreground">Domyślnie zaznaczone są tylko te wózki: dokładnie dopasowane, bez akcesoriów i posortowane według wartości źródła.</p>{renderOfferTable(primaryOffers, "Brak dokładnie dopasowanych wózków.", true)}</div>
              <div className="mt-6 border-t border-border pt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Pozostałe oferty uzupełniające</h4><span className="text-[11px] text-muted-foreground">{supplementaryOffers.length}</span></div><p className="mt-1 text-[11px] text-muted-foreground">Prawidłowe oferty wózków, które nie weszły do pierwszej dziesiątki. Możesz je wybrać ręcznie.</p>{renderOfferTable(supplementaryOffers, "Brak ofert uzupełniających.", true)}</div>
              <div className="mt-6 border-t border-border pt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Odrzucone akcesoria</h4><span className="text-[11px] text-muted-foreground">{accessoryOffers.length}</span></div><p className="mt-1 text-[11px] text-muted-foreground">Akcesoria kompatybilne z {brand.trim()} {model.trim()} nie są źródłami danych o wózku i nie mogą zostać wybrane.</p>{renderOfferTable(accessoryOffers, "Brak odrzuconych akcesoriów.", false)}</div>
              {otherOffers.length > 0 && <details className="mt-6 border-t border-border pt-5"><summary className="cursor-pointer text-xs font-medium text-muted-foreground">Oferty niepewne lub niedopasowane ({otherOffers.length})</summary><p className="mt-2 text-[11px] text-muted-foreground">Nie zostały wybrane, ponieważ nie potwierdzają jednoznacznie modelu albo typu produktu.</p>{renderOfferTable(otherOffers, "Brak dodatkowych ofert.", false)}</details>}
            </section>
            <div className="mt-6 flex gap-2">
              <button onClick={() => setStep(0)} className="px-4 py-2 text-xs font-medium border border-border rounded hover:bg-muted transition-colors">
                Wstecz
              </button>
              <button
                onClick={() => setStep(2)}
                disabled={selectedSourcesCount === 0}
                className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors disabled:opacity-40"
              >
                Przejdź do potwierdzenia
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Potwierdzenie */}
        {step === 2 && (
          <div className="max-w-lg">
            <h2 className="text-sm font-semibold text-foreground mb-1">Potwierdzenie wyboru</h2>
            <p className="text-xs text-muted-foreground mb-4">Sprawdź wybrane źródła przed rozpoczęciem analizy. Wybrane oficjalne źródła producenta zostaną uwzględnione razem z ofertami Allegro.</p>
            <div className="bg-card border border-border rounded-lg divide-y divide-border">
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Produkt</span>
                <span className="text-xs font-medium text-foreground">
                  {brand} {model}
                </span>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Wybrane oficjalne źródła</span>
                <span className="text-xs font-medium text-foreground">{selectedManufacturerSourceIds.size}</span>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Wybrane oferty Allegro</span>
                <span className="text-xs font-medium text-foreground">{selectedOfferIds.size}</span>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Łącznie wybranych źródeł</span>
                <span className="text-xs font-semibold text-foreground">{selectedSourcesCount}</span>
              </div>
            </div>
            {selectedOfferIds.size > 10 && <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">Duża liczba źródeł zwiększy czas i koszt analizy.</p>}
            {requestError && <p className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{requestError}</p>}
            <div className="mt-6 flex gap-2">
              <button onClick={() => setStep(1)} className="px-4 py-2 text-xs font-medium border border-border rounded hover:bg-muted transition-colors">
                Wstecz
              </button>
              <button
                onClick={() => void startRun()}
                disabled={runLoading || selectedSourcesCount === 0}
                className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {runLoading ? "Uruchamianie…" : "Uruchom analizę"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Analiza */}
        {step === 3 && (
          <div className="max-w-xl">
            <h2 className="text-sm font-semibold text-foreground mb-1">Analiza</h2>
            <p className="text-xs text-muted-foreground mb-5">Stan pochodzi bezpośrednio z lokalnego pipeline’u. Możesz wrócić do tej karty później.</p>
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-muted-foreground">{run?.current_step || "W kolejce"}</span>
                <span className="text-xs font-mono text-foreground">{Math.round(run?.progress || 0)}%</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${run?.progress || 0}%` }}
                />
              </div>
              <p className="mt-4 text-xs text-muted-foreground">Status: {run?.status === "queued" ? "oczekuje" : run?.status === "running" ? "w toku" : run?.status || "—"}</p>
              <details className="mt-4 rounded border border-border bg-muted/30 p-3"><summary className="cursor-pointer text-xs font-medium text-foreground">Dziennik techniczny</summary><pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-[11px] text-muted-foreground">{run?.logs_tail.join("\n") || "Brak wpisów."}</pre></details>
            </div>
          </div>
        )}

        {/* Step 4: Wynik */}
        {step === 4 && (
          <div className="max-w-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className={`w-9 h-9 rounded-full border flex items-center justify-center ${runFailed ? "bg-red-50 border-red-200" : runPartial ? "bg-amber-50 border-amber-200" : "bg-emerald-50 border-emerald-200"}`}>
                {runFailed ? <XCircle size={18} className="text-red-600" /> : runPartial ? <AlertCircle size={18} className="text-amber-600" /> : <CheckCircle2 size={18} className="text-emerald-600" />}
              </div>
              <div>
                <h2 className="text-sm font-semibold text-foreground">{runFailed ? "Research zatrzymał się" : runPartial ? "Research zakończony częściowo" : "Research zakończony"}</h2>
                <p className="text-xs text-muted-foreground">{runFailed ? run?.error : run?.snapshot_updated ? "Katalog produktów został odświeżony." : "Wyniki są gotowe do przeglądu."}</p>
              </div>
            </div>
            <div className="bg-card border border-border rounded-lg divide-y divide-border">
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Wybrane nowe oferty</span>
                <span className="text-xs font-mono font-medium text-foreground">{selectedOfferIds.size}</span>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Status pipeline’u</span>
                <span className="text-xs font-mono font-medium text-foreground">{run?.status || "—"}</span>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Produkt</span>
                <span className="text-xs font-mono text-foreground">{brand} {model}</span>
              </div>
            </div>
            {runFailed && <details className="mt-4 rounded border border-border bg-muted/30 p-3"><summary className="cursor-pointer text-xs font-medium text-foreground">Pokaż dziennik techniczny</summary><pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-[11px] text-muted-foreground">{run?.logs_tail.join("\n") || "Brak wpisów."}</pre></details>}
            <div className="mt-6 flex gap-2">
              <button
                onClick={reset}
                className="px-4 py-2 text-xs font-medium border border-border rounded hover:bg-muted transition-colors"
              >
                Nowy research
              </button>
              {runFailed ? <button onClick={retryRun} disabled={runLoading} className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors disabled:opacity-40">Ponów</button> : <button onClick={() => { window.location.assign(`/products/${run?.product_slug || `${brand.toLowerCase()}__${model.toLowerCase().replace(/\s+/g, "-")}`}`); }} className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors">Otwórz produkt</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page: Uruchomienia ───────────────────────────────────────────────────────
function RunLog({ runId }: { runId: string }) {
  const [logs, setLogs] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    apiRequest<ApiRun>(`/runs/${runId}`).then((run) => {
      if (!cancelled) setLogs(run.logs_tail || []);
    }).catch((err) => {
      if (!cancelled) setError(err instanceof Error ? err.message : "Nie udało się wczytać logu.");
    });
    return () => { cancelled = true; };
  }, [runId]);
  if (error) return <p className="mt-2 text-[11px] text-red-700">{error}</p>;
  return <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground">{logs === null ? "Wczytywanie logu…" : logs.join("\n") || "Brak zapisanych wpisów."}</pre>;
}

function PageUruchomienia() {
  const [runs, setRuns] = useState<ApiRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const loadRuns = async () => {
    setLoading(true); setError("");
    try {
      const response = await apiRequest<{ total: number; runs: ApiRun[] }>("/runs?limit=50&sort=created_at_desc");
      setRuns(response.runs || []); setTotal(response.total || 0);
    } catch (err) { setError(err instanceof Error ? err.message : "Nie udało się wczytać historii uruchomień."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadRuns(); }, []);
  const retry = async (runId: string) => {
    setWorking(runId); setError("");
    try { await apiRequest<ApiRun>(`/runs/${runId}/retry`, { method: "POST" }); await loadRuns(); }
    catch (err) { setError(err instanceof Error ? err.message : "Nie udało się ponowić uruchomienia."); }
    finally { setWorking(null); }
  };
  const cancel = async (runId: string) => {
    setWorking(runId); setError("");
    try { await apiRequest<ApiRun>(`/runs/${runId}/cancel`, { method: "POST" }); await loadRuns(); }
    catch (err) { setError(err instanceof Error ? err.message : "Nie udało się anulować uruchomienia."); }
    finally { setWorking(null); }
  };
  const failed = (status: string) => ["failed", "timed_out", "cancelled", "interrupted"].includes(status);
  const succeeded = (status: string) => status === "succeeded" || status === "success";
  const statusLabel = (status: string) => succeeded(status) ? "Sukces" : status === "running" ? "W toku" : status === "queued" ? "W kolejce" : status === "timed_out" ? "Przekroczony czas" : status === "cancelled" ? "Anulowano" : status === "interrupted" ? "Przerwano" : "Błąd";
  const duration = (run: ApiRun) => {
    if (!run.started_at || !run.finished_at) return "—";
    const seconds = Math.max(0, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000));
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold text-foreground">Uruchomienia</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{total} uruchomień łącznie</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <CheckCircle2 size={12} className="text-emerald-500" />
            {runs.filter((run) => succeeded(run.status)).length} sukces
          </div>
          <span>·</span>
          <div className="flex items-center gap-1">
            <XCircle size={12} className="text-red-400" />
            {runs.filter((run) => failed(run.status)).length} błędy
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Timeline */}
        <div className="px-6 py-4">
          <div className="relative">
            {/* vertical line */}
            <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />

            <div className="flex flex-col gap-0">
              {loading ? <p className="py-4 text-xs text-muted-foreground">Wczytywanie historii uruchomień…</p> : error ? <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div> : runs.length === 0 ? <p className="py-4 text-xs text-muted-foreground">Brak zapisanych uruchomień.</p> : runs.map((run) => (
                <div key={run.run_id} className="flex gap-4 relative pb-4">
                  {/* dot */}
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 z-10 border-2 ${succeeded(run.status) ? "bg-white border-emerald-400" : failed(run.status) ? "bg-white border-red-300" : "bg-white border-blue-300"}`}>
                    {succeeded(run.status) ? <CheckCircle2 size={15} className="text-emerald-600" /> : failed(run.status) ? <XCircle size={15} className="text-red-600" /> : <Clock size={15} className="text-blue-600" />}
                  </div>

                  {/* card */}
                  <div className={`flex-1 bg-card border rounded-lg p-3 ${failed(run.status) ? "border-red-100" : "border-border"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => window.location.assign(`/products/${run.product_slug}`)} className="text-xs font-medium text-foreground hover:text-primary">{run.brand} {run.model}</button>
                          <span className="text-[11px] font-mono text-muted-foreground">{run.run_id}</span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground">
                          <span>{run.started_at ? new Date(run.started_at).toLocaleString("pl-PL") : "—"}</span>
                          <span>·</span>
                          <span>{duration(run)}</span>
                          <span>·</span>
                          <span>{run.sources_selected ?? 0} źródeł</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${succeeded(run.status) ? "bg-emerald-50 text-emerald-700 border-emerald-200" : failed(run.status) ? "bg-red-50 text-red-600 border-red-200" : "bg-blue-50 text-blue-700 border-blue-200"}`}>
                          {statusLabel(run.status)}
                        </span>
                        {failed(run.status) && (
                          <button
                            onClick={() => void retry(run.run_id)}
                            disabled={working === run.run_id}
                            className="flex items-center gap-1 px-2 py-0.5 text-[11px] border border-border rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
                          >
                            <RefreshCw size={10} className={working === run.run_id ? "animate-spin" : ""} />
                            {working === run.run_id ? "Ponawiam…" : "Ponów"}
                          </button>
                        )}
                        {run.status === "running" && <button onClick={() => void cancel(run.run_id)} disabled={working === run.run_id} className="px-2 py-0.5 text-[11px] border border-border rounded hover:bg-muted">Anuluj</button>}
                      </div>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">Etap: {run.current_step || "—"} · Postęp: {run.progress}% · Coverage: {run.coverage_before ?? "—"}% → {run.coverage_after ?? "—"}%</p>
                    {run.retry_of && <p className="mt-1 text-[11px] text-muted-foreground">Ponowienie runu: {run.retry_of}</p>}
                    {run.error && (
                      <div className="mt-2 p-2 bg-red-50 border border-red-100 rounded text-[11px] text-red-700 font-mono">
                        {run.error}
                      </div>
                    )}
                    {(failed(run.status) || run.status === "running") && <button onClick={() => setExpandedLog(expandedLog === run.run_id ? null : run.run_id)} className="mt-2 text-[11px] text-primary hover:underline">{expandedLog === run.run_id ? "Ukryj log" : "Pokaż log"}</button>}
                    {expandedLog === run.run_id && <RunLog runId={run.run_id} />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Legacy Figma integration mock intentionally excluded from FIELDNOTE.
 * Local credentials are configured only in fieldnote-api/.env and are never
 * editable or displayed in the product UI.
 * ─── Page: Integracje (removed) ─────────────────────────────────────────────
 */
/*
function PageIntegracje() {
  const [fcKey, setFcKey] = useState("fc-••••••••••••••••••••••");
  const [oaiKey, setOaiKey] = useState("sk-proj-••••••••••••••••");
  const [showFc, setShowFc] = useState(false);
  const [showOai, setShowOai] = useState(false);
  const [fcSaved, setFcSaved] = useState(false);
  const [oaiSaved, setOaiSaved] = useState(false);

  const save = (which: "fc" | "oai") => {
    if (which === "fc") { setFcSaved(true); setTimeout(() => setFcSaved(false), 2000); }
    else { setOaiSaved(true); setTimeout(() => setOaiSaved(false), 2000); }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
        <h1 className="text-base font-semibold text-foreground">Integracje</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Konfiguracja połączeń zewnętrznych</p>
      </div>

      <div className="flex-1 overflow-auto px-6 py-5 flex flex-col gap-4 max-w-xl">
        {/* Firecrawl * /}
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-orange-50 border border-orange-100 flex items-center justify-center flex-shrink-0">
                <Layers size={15} className="text-orange-500" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">Firecrawl</p>
                <p className="text-[11px] text-muted-foreground">Web scraping i ekstrakcja danych</p>
              </div>
            </div>
            <span className="text-[11px] px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded font-medium flex-shrink-0">
              Połączony
            </span>
          </div>
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Klucz API</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showFc ? "text" : "password"}
                    value={fcKey}
                    onChange={(e) => setFcKey(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs font-mono bg-input-background border border-border rounded outline-none focus:ring-1 focus:ring-primary/30"
                  />
                  <button
                    onClick={() => setShowFc(!showFc)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-[10px]"
                  >
                    {showFc ? "Ukryj" : "Pokaż"}
                  </button>
                </div>
                <button
                  onClick={() => save("fc")}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-colors flex-shrink-0 ${fcSaved ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground hover:bg-primary/90"}`}
                >
                  {fcSaved ? "Zapisano" : "Zapisz"}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 pt-1">
              {[
                { label: "Łączne zapytania", value: "1 284" },
                { label: "W tym tygodniu", value: "137" },
                { label: "Limit mies.", value: "5 000" },
              ].map((s) => (
                <div key={s.label} className="p-2.5 bg-muted/40 rounded border border-border">
                  <p className="text-[10px] text-muted-foreground">{s.label}</p>
                  <p className="text-sm font-mono font-semibold text-foreground mt-0.5">{s.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* OpenAI * /}
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-emerald-50 border border-emerald-100 flex items-center justify-center flex-shrink-0">
                <FileText size={15} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">OpenAI</p>
                <p className="text-[11px] text-muted-foreground">Analiza i strukturyzacja danych (gpt-4o)</p>
              </div>
            </div>
            <span className="text-[11px] px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded font-medium flex-shrink-0">
              Połączony
            </span>
          </div>
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Klucz API</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showOai ? "text" : "password"}
                    value={oaiKey}
                    onChange={(e) => setOaiKey(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs font-mono bg-input-background border border-border rounded outline-none focus:ring-1 focus:ring-primary/30"
                  />
                  <button
                    onClick={() => setShowOai(!showOai)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-[10px]"
                  >
                    {showOai ? "Ukryj" : "Pokaż"}
                  </button>
                </div>
                <button
                  onClick={() => save("oai")}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-colors flex-shrink-0 ${oaiSaved ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground hover:bg-primary/90"}`}
                >
                  {oaiSaved ? "Zapisano" : "Zapisz"}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Model</label>
              <select className="px-3 py-1.5 text-xs bg-input-background border border-border rounded outline-none w-full font-mono focus:ring-1 focus:ring-primary/30">
                <option>gpt-4o</option>
                <option>gpt-4o-mini</option>
                <option>gpt-4-turbo</option>
              </select>
            </div>
            <div className="grid grid-cols-3 gap-3 pt-1">
              {[
                { label: "Tokeny łącznie", value: "2.1M" },
                { label: "Koszt mies.", value: "$4.28" },
                { label: "Wywołania", value: "312" },
              ].map((s) => (
                <div key={s.label} className="p-2.5 bg-muted/40 rounded border border-border">
                  <p className="text-[10px] text-muted-foreground">{s.label}</p>
                  <p className="text-sm font-mono font-semibold text-foreground mt-0.5">{s.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Add integration placeholder * /}
        <button className="flex items-center gap-2 p-4 bg-card border border-dashed border-border rounded-lg text-xs text-muted-foreground hover:border-primary/30 hover:text-primary transition-colors">
          <Plus size={14} />
          Dodaj integrację
        </button>
      </div>
    </div>
  );
}

*/
// ─── Page: Pomoc ──────────────────────────────────────────────────────────────
function PagePomoc() {
  const faqs = [
    { q: "Co to jest Coverage?", a: "Coverage to odsetek pól z zaakceptowaną wartością. Nie jest oceną wiarygodności: tę pokazuje osobno jakość dowodów." },
    { q: "Czym jest jakość dowodów?", a: "To udział pól z poprawnym, zapisanym dowodem i przypisanym źródłem. Dowody legacy bez źródła nie podnoszą tej miary." },
    { q: "Co oznacza niezależne potwierdzenie?", a: "Powtarzające się opisy z tej samej rodziny treści liczą się jako jedno niezależne potwierdzenie." },
    { q: "Gdzie są ustawienia integracji?", a: "Klucze pozostają wyłącznie w lokalnej konfiguracji API. Aplikacja nie zapisuje ani nie wyświetla ich w interfejsie." },
  ];

  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
        <h1 className="text-base font-semibold text-foreground">Pomoc</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Dokumentacja i najczęstsze pytania</p>
      </div>
      <div className="flex-1 overflow-auto px-6 py-5 max-w-xl flex flex-col gap-3">
        {faqs.map((f, i) => (
          <div key={i} className="bg-card border border-border rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-3 text-left"
              onClick={() => setOpen(open === i ? null : i)}
            >
              <span className="text-xs font-medium text-foreground">{f.q}</span>
              {open === i ? <ChevronUp size={13} className="text-muted-foreground flex-shrink-0" /> : <ChevronDown size={13} className="text-muted-foreground flex-shrink-0" />}
            </button>
            {open === i && (
              <div className="px-4 pb-3 text-xs text-muted-foreground border-t border-border pt-3">
                {f.a}
              </div>
            )}
          </div>
        ))}
        <div className="mt-2 p-4 bg-accent border border-primary/20 rounded-lg">
          <p className="text-xs font-medium text-foreground mb-1">Pomoc lokalna</p>
          <p className="text-xs text-muted-foreground">FIELDNOTE działa lokalnie. Informacje o konfiguracji i wynikach procesu są dostępne w zakładkach Research oraz Uruchomienia.</p>
        </div>
      </div>
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState<Page>("produkty");
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [researchSession, setResearchSession] = useState(0);
  const [previousResearchProductSlug, setPreviousResearchProductSlug] = useState("");

  const beginResearch = (previousProductSlug = "") => {
    setPreviousResearchProductSlug(previousProductSlug);
    setResearchSession((session) => session + 1);
    window.history.pushState({}, "", "/research");
    setPage("research");
  };

  const nav = (nextPage: Page) => {
    if (nextPage === "research") {
      beginResearch(page === "produkt-szczegoly" ? selectedProductId : "");
      return;
    }
    window.history.pushState({}, "", routeForPage(nextPage));
    setPage(nextPage);
  };

  const openDetail = (id: string) => {
    setSelectedProductId(id);
    setPage("produkt-szczegoly");
    window.history.pushState({}, "", `/products/${id}`);
  };

  const openSources = (id: string) => {
    const [brandSlug, modelSlug] = id.split("__");
    if (!brandSlug || !modelSlug) return;
    setSelectedProductId(id);
    setPage("produkt-zrodla");
    window.history.pushState({}, "", `/products/${brandSlug}/${modelSlug}/sources`);
  };

  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const handler = (e: MediaQueryListEvent) => {
      setIsNarrow(e.matches);
      setSidebarOpen(!e.matches);
    };
    setIsNarrow(mq.matches);
    setSidebarOpen(!mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    const syncRoute = () => {
      const route = parseFieldnoteRoute(window.location.pathname, new Set(PRODUCTS.map((product) => product.slug)));
      if (route.productSlug) setSelectedProductId(route.productSlug);
      setPage(route.page);
    };
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);

  const sidebarCollapsed = isNarrow ? !sidebarOpen : false;

  return (
    <div
      className="flex h-screen bg-background overflow-hidden"
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      {/* Mobile/Tablet drawer overlay */}
      {isNarrow && sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/20 backdrop-blur-[1px]"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={isNarrow ? "fixed left-0 top-0 h-full z-30" : "relative flex-shrink-0"}
        style={isNarrow ? { transform: sidebarOpen ? "translateX(0)" : "translateX(-100%)", transition: "transform 200ms ease" } : {}}
      >
        <Sidebar
          current={page}
          onNav={(p) => { nav(p); if (isNarrow) setSidebarOpen(false); }}
          collapsed={false}
        />
      </div>

      {/* Main */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-card flex-shrink-0">
          {isNarrow && (
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              aria-label={sidebarOpen ? "Zamknij menu" : "Otwórz menu"}
            >
              {sidebarOpen ? <X size={15} /> : <Menu size={15} />}
            </button>
          )}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="text-foreground font-medium">
              {page === "produkty" ? "Produkty" :
               page === "produkt-szczegoly" ? `Produkty / ${PRODUCTS.find(p => p.id === selectedProductId)?.name || ""}` :
               page === "produkt-zrodla" ? `Produkty / ${PRODUCTS.find(p => p.id === selectedProductId)?.name || ""} / Aukcje i źródła` :
               page === "research" ? "Research" :
               page === "uruchomienia" ? "Uruchomienia" : "Pomoc"}
            </span>
          </div>
          <div className="ml-auto text-[11px] text-muted-foreground hidden sm:block">Dane lokalne</div>
        </div>

        {/* Page content */}
        <div className="flex-1 overflow-hidden">
          {page === "produkty" && <PageProdukty onDetail={openDetail} onResearch={() => beginResearch()} />}
          {page === "produkt-szczegoly" && (
            <PageProduktSzczegoly
              productId={selectedProductId}
              onBack={() => {
                window.history.pushState({}, "", "/products");
                setPage("produkty");
              }}
              onResearch={() => beginResearch(selectedProductId)}
              onSources={() => openSources(selectedProductId)}
            />
          )}
          {page === "produkt-zrodla" && <PageProduktZrodla productId={selectedProductId} onBack={() => openDetail(selectedProductId)} />}
          {page === "research" && <PageResearch key={researchSession} previousProductSlug={previousResearchProductSlug} />}
          {page === "uruchomienia" && <PageUruchomienia />}
          {page === "pomoc" && <PagePomoc />}
        </div>
      </div>
    </div>
  );
}
