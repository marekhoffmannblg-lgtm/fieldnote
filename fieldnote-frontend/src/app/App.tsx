import { Fragment, createContext, useContext, useState, useEffect, useRef, type ReactNode } from "react";
import catalogData from "../data/generated/catalog.json";
import { apiRequest } from "../api/client";
import type { EvidenceItemV1, ProductMetricsV1, SourceContributionV1 } from "../api/contracts";
import { parseFieldnoteRoute, routeForPage, type FieldnotePage } from "../routes/navigation";
import { canCancelRun, getRunCostProgress, isRunActive, isRunFailure, isRunPartial, isRunSuccess, shouldAutoReloadAfterRun } from "./runStatus";
import { groupsForCategory, isValidCategorySelection, type CategoryOption } from "./categorySelection";
import { canSelectPreviewOffer } from "./offerSelection";
import { canCompareSelection, toggleComparisonSelection } from "./comparisonSelection";
import { useAuth } from "../auth/AuthProvider";
import { AuthLoadingScreen, ChangeInitialPasswordScreen, LoginScreen } from "../auth/AuthScreens";
import { authConfigurationError } from "../auth/supabase";
import { canAccessAdminUsers } from "../auth/guards";
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
  productId?: string;
  slug: string;
  brand: string;
  name: string;
  model: string;
  configuration?: string;
  scope?: string;
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
  category_key?: string;
  subcategory_key?: string;
  subcategoryLabel?: string;
  benchmark_group?: string;
  benchmarkCategory: string;
  statusReason?: string;
  statusUpdatedAt?: string | null;
}

interface CatalogProduct {
  brand: string;
  model: string;
  configuration?: string;
  scope?: string;
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
  category_key?: string;
  subcategory_key?: string;
  subcategory_label?: string;
  benchmark_group?: string;
  benchmark_group_key?: string;
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

interface VisualSnapshot {
  visual_snapshot_id: string;
  source_id: string;
  capture_status: "captured" | "partial" | "failed" | "skipped";
  capture_provider: string;
  full_page_artifact_id: string | null;
  blocks_count: number;
  media_count: number;
}

interface VisualBlock {
  block_id: string;
  region: "gallery" | "description" | "feature" | "dimensions" | "included" | "accessory" | "variant" | "recommendation" | "other";
  heading: string | null;
  body_text: string | null;
  media_ids: string[];
  classification: string;
  classification_reason: string | null;
  section_artifact_id: string | null;
}

interface VisualMedia {
  media_id: string;
  block_id: string | null;
  media_type: "image" | "video" | "video_poster" | "background_image" | "document" | "other";
  original_url: string | null;
  alt_text: string | null;
  caption_text: string | null;
  role: string;
}

interface VisualEnvelope { snapshot: VisualSnapshot }
interface VisualPage<T> { items: T[]; total: number }

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

interface BenchmarkProductRef {
  product_id: string;
  brand: string;
  model: string;
  configuration: string;
  benchmark_group: string;
  product_slug: string;
  status: string;
  coverage: number | null;
  source_count: number;
}

interface InternalBenchmarkSummary {
  benchmark_id: null;
  benchmark_type: "internal";
  benchmark_group_key: string;
  benchmark_group_label: string;
  title: string;
  status: "dynamic";
  participant_count: number;
  has_comparison: boolean;
}

interface InternalBenchmarkDetail {
  benchmark_id: null;
  benchmark_type: "internal";
  benchmark_group_key: string;
  title: string;
  status: "dynamic";
  anchor: null;
  participants: BenchmarkProductRef[];
  participant_count: number;
  created_at: null;
  updated_at: string | null;
}

interface CompetitiveBenchmarkSummary {
  benchmark_id: string;
  title: string;
  status: "draft" | "active" | "archived";
  benchmark_group_key: string;
  anchor_product_id: string;
  participant_count: number;
  created_at: string;
  updated_at: string;
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
  product_type_label: string;
  category_compatible: boolean;
  selectable: boolean;
  match_status: "exact_match" | "probable_match" | "rejected";
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
  fetch_status?: string;
  clean_status?: string;
  cached?: boolean;
  last_fetched_at?: string;
  refresh_recommended?: boolean;
}

interface PreviewResponse {
  status: "ok" | "LIVE_SEARCH_FAILED" | "CACHE_NOT_AVAILABLE";
  mode?: "local_cache" | "live_firecrawl" | "live_failed" | "cache_not_available";
  requested_mode: "live" | "cache";
  result_mode: "local_cache" | "live_firecrawl" | "live_failed" | "cache_not_available";
  is_fresh: boolean;
  fetched_at?: string;
  cached_at?: string;
  cached_result_available: boolean;
  message?: string;
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
    probable_count: number;
    titles: string[];
  };
}

interface ApiRun {
  run_id: string;
  brand: string;
  model: string;
  status: "queued" | "leased" | "running" | "succeeded" | "success" | "partial" | "failed" | "timed_out" | "cancelled" | "interrupted";
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
  product_profile_stage?: string;
  product_profile_status?: "generated" | "cached" | "insufficient_profile_evidence" | "failed" | "skipped" | string;
  product_profile_warning?: string;
  cost_limit?: number | null;
  cost_used?: number | null;
  usage?: { sources_selected?: number; sources_fetched?: number; sources_failed?: number; sources_attached?: number; coverage_before?: number | null; coverage_after?: number | null; cost_used?: number | null };
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

const productFromCatalog = (product: CatalogProduct): Product => ({
  id: product.slug,
  productId: product.product_id,
  slug: product.slug,
  brand: product.brand,
  name: product.model,
  model: product.model,
  configuration: product.configuration || "",
  scope: product.scope || "test",
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
  category_key: product.category_key || "",
  subcategory_key: product.subcategory_key || "",
  subcategoryLabel: product.subcategory_label || "",
  benchmark_group: product.benchmark_group || "",
  benchmarkCategory: product.benchmark_category || "Bez podkategorii",
  statusReason: product.status_reason || "",
  statusUpdatedAt: product.status_updated_at || product.updated_at || null,
});

// The generated snapshot is useful before the local API starts. Once it is
// reachable, runtime catalogue data is authoritative and includes products
// registered before their first research snapshot.
const FALLBACK_PRODUCTS: Product[] = (catalogData as CatalogProduct[]).map(productFromCatalog);
const CatalogContext = createContext<{ products: Product[]; refreshCatalog: () => Promise<void> }>({
  products: FALLBACK_PRODUCTS,
  refreshCatalog: async () => undefined,
});
const useCatalog = () => useContext(CatalogContext);

// ─── Helpers ──────────────────────────────────────────────────────────────────
function coverageColor(v: number) {
  if (v >= 65) return "text-emerald-700 bg-emerald-50";
  if (v >= 50) return "text-amber-700 bg-amber-50";
  return "text-red-700 bg-red-50";
}

function normalizedBrand(value: string) {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim().toLocaleLowerCase("pl");
}

function isLioneloProduct(product: Pick<Product, "brand">) {
  return normalizedBrand(product.brand) === "lionelo";
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
  { id: "benchmarki", label: "Benchmarki", icon: <GitCompare size={15} /> },
  { id: "produkty-konkurencji", label: "Produkty konkurencji", icon: <Package size={15} /> },
  { id: "research", label: "Research", icon: <Search size={15} /> },
  { id: "zrodla", label: "Źródła", icon: <Layers size={15} /> },
];

function Sidebar({
  current,
  onNav,
  collapsed,
  canManageUsers,
}: {
  current: Page;
  onNav: (p: Page) => void;
  collapsed: boolean;
  canManageUsers: boolean;
}) {
  const active = (id: Page) =>
    current === id
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
        {(canManageUsers ? [...NAV_ITEMS, { id: "users" as Page, label: "Użytkownicy", icon: <Package size={15} /> }] : NAV_ITEMS).map((item) => (
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
function PageProdukty({ onDetail, onResearch, onCompare }: { onDetail: (id: string) => void; onResearch: () => void; onCompare: (ids: string[]) => void }) {
  const { products } = useCatalog();
  const [query, setQuery] = useState("");
  const [showUnassigned, setShowUnassigned] = useState(false);
  const [familyKey, setFamilyKey] = useState("");
  const [groupKey, setGroupKey] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const classified = products.filter((product) => showUnassigned || Boolean(product.benchmark_group));
  const familyKeyFor = (product: Product) => product.subcategory_key || product.category_key || "unassigned";
  const familyLabel = (product: Product) => familyKeyFor(product) === "unassigned" ? "Do klasyfikacji" : (product.subcategoryLabel || product.category || "Nieprzypisane").replace(/ dziecięce$/i, "");
  const searchable = query.trim() ? classified.filter((product) => `${product.brand} ${product.name} ${product.configuration || ""}`.toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl"))) : [];
  const families = [...new Map(classified.map((product) => [familyKeyFor(product), { key: familyKeyFor(product), label: familyLabel(product) }])).values()];
  const familyProducts = familyKey ? classified.filter((product) => familyKeyFor(product) === familyKey) : classified;
  const groups = [...new Map(familyProducts.filter((product) => product.benchmark_group).map((product) => [product.benchmark_group || "", { key: product.benchmark_group || "", label: product.benchmarkCategory }])).values()]
    .sort((left, right) => ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(left.key) - ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(right.key));
  const groupProducts = groupKey ? familyProducts.filter((product) => product.benchmark_group === groupKey) : familyProducts;
  const toggleComparison = (product: Product) => setSelected((current) => toggleComparisonSelection(current, product, products));
  const productCard = (product: Product) => {
    const badge = statusBadge(product.status);
    const checked = selected.has(product.id);
    const selectable = Boolean(product.benchmark_group);
    return <article key={product.id} className="rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/30">
      <div className="flex items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">{product.brand}</p><p className="mt-0.5 text-sm font-semibold text-foreground">{product.name}</p>{product.configuration && <p className="mt-1 text-xs text-muted-foreground">Konfiguracja: {product.configuration}</p>}</div><div className="flex items-center gap-2"><label className={`inline-flex items-center gap-1 text-[11px] ${selectable ? "cursor-pointer text-muted-foreground" : "text-muted-foreground/50"}`}><input aria-label={`Wybierz ${product.brand} ${product.name} do porównania`} type="checkbox" disabled={!selectable} checked={checked} onChange={() => toggleComparison(product)} />Porównaj</label><span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.label}</span></div></div>
      <p className="mt-3 text-xs text-muted-foreground">{product.benchmarkCategory || "Do klasyfikacji"}</p>{product.scope === "test" && <span className="mt-2 inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">Dane testowe</span>}{(product.zrodla !== null || product.coverage !== null) && <p className="mt-2 text-[11px] text-muted-foreground">{product.zrodla !== null ? `${product.zrodla} źródeł` : ""}{product.zrodla !== null && product.coverage !== null ? " · " : ""}{product.coverage !== null ? `coverage ${product.coverage}%` : ""}</p>}
      <button onClick={() => onDetail(product.id)} className="mt-3 text-xs font-medium text-primary hover:underline">Otwórz szczegóły</button>
    </article>;
  };
  const selectedGroup = products.find((product) => selected.has(product.id))?.benchmark_group;
  const showProductList = Boolean(groupKey) || familyKey === "unassigned";
  return <div className="h-full overflow-auto bg-background"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-4"><div><h1 className="text-base font-semibold text-foreground">Produkty</h1><p className="mt-0.5 text-xs text-muted-foreground">Katalog według rodzin produktowych i grup benchmarkowych</p></div><div className="flex items-center gap-2">{canCompareSelection(selected) && <button onClick={() => onCompare([...selected])} className="rounded border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"><GitCompare size={13} className="mr-1 inline" />Porównaj wybrane ({selected.size})</button>}<button onClick={onResearch} className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"><Plus size={13} className="mr-1 inline" />Nowy research</button></div></header><main className="mx-auto max-w-6xl px-6 py-6"><div className="mb-5 flex flex-wrap items-center gap-3"><div className="relative min-w-64 flex-1"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Szukaj produktu..." className="w-full rounded border border-border bg-card py-2 pl-8 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary/30" /></div><label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={showUnassigned} onChange={(event) => { setShowUnassigned(event.target.checked); setFamilyKey(""); setGroupKey(""); }} />Pokaż nieprzypisane rekordy</label></div>{selected.size > 0 && <p className="mb-4 text-xs text-muted-foreground">Zaznaczono {selected.size} / 5{selectedGroup ? ` · grupa: ${groups.find((group) => group.key === selectedGroup)?.label || selectedGroup}` : ""}. Produkty z innej grupy benchmarkowej nie mogą zostać dodane do tego porównania.</p>}<nav aria-label="Breadcrumb" className="mb-6 flex items-center gap-1 text-xs text-muted-foreground"><button onClick={() => { setFamilyKey(""); setGroupKey(""); }} className={!familyKey ? "font-medium text-foreground" : "hover:text-primary"}>Produkty</button>{familyKey && <><ChevronRight size={12} /><button onClick={() => setGroupKey("")} className={!groupKey ? "font-medium text-foreground" : "hover:text-primary"}>{families.find((family) => family.key === familyKey)?.label || familyKey}</button></>}{groupKey && <><ChevronRight size={12} /><span className="font-medium text-foreground">{groups.find((group) => group.key === groupKey)?.label || groupKey}</span></>}</nav>{query.trim() ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Wyniki wyszukiwania</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{searchable.map(productCard)}</div>{searchable.length === 0 && <p className="rounded border border-dashed border-border p-6 text-sm text-muted-foreground">Brak sklasyfikowanych produktów spełniających wyszukiwanie.</p>}</section> : !familyKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Rodziny produktów</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{families.map((family) => { const items = classified.filter((product) => familyKeyFor(product) === family.key && product.benchmark_group); const groupCount = new Set(items.map((product) => product.benchmark_group)).size; return <button key={family.key} onClick={() => setFamilyKey(family.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{family.label}</p><p className="mt-2 text-xs text-muted-foreground">{items.length} sklasyfikowanych produktów</p><p className="mt-1 text-xs text-muted-foreground">{groupCount} grupy benchmarkowe</p></button>; })}</div></section> : showProductList ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">{groupKey ? `${groups.find((group) => group.key === groupKey)?.label || groupKey} (${groupProducts.length})` : "Do klasyfikacji"}</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{groupProducts.map(productCard)}</div>{groupProducts.length === 0 && <p className="rounded border border-dashed border-border p-5 text-sm text-muted-foreground">Brak produktów w tej grupie.</p>}</section> : <section><h2 className="mb-3 text-sm font-semibold text-foreground">Grupy benchmarkowe</h2><div className="grid gap-3 sm:grid-cols-2">{groups.map((group) => { const items = familyProducts.filter((product) => product.benchmark_group === group.key); return <button key={group.key} onClick={() => setGroupKey(group.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{group.label}</p><p className="mt-2 text-xs text-muted-foreground">{items.length} produktów</p></button>; })}</div></section>}</main></div>;
}

function PageProduktyBrandSplitLegacy({ onDetail, onResearch }: { onDetail: (id: string) => void; onResearch: () => void }) {
  const { products } = useCatalog();
  const [query, setQuery] = useState("");
  const [showUnassigned, setShowUnassigned] = useState(false);
  const [familyKey, setFamilyKey] = useState("");
  const [groupKey, setGroupKey] = useState("");
  const normalizedBrand = (brand: string) => brand.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pl").trim();
  const isOwn = (product: Product) => normalizedBrand(product.brand) === "lionelo";
  const classified = products.filter((product) => showUnassigned || Boolean(product.benchmark_group));
  const searchable = query.trim() ? classified.filter((product) => `${product.brand} ${product.name} ${product.configuration || ""}`.toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl"))) : [];
  const familyLabel = (product: Product) => (product.subcategoryLabel || product.category || "Nieprzypisane").replace(/ dziecięce$/i, "");
  const families = [...new Map(classified.map((product) => [product.subcategory_key || product.category_key || "unassigned", { key: product.subcategory_key || product.category_key || "unassigned", label: familyLabel(product) }])).values()];
  const familyProducts = familyKey ? classified.filter((product) => (product.subcategory_key || product.category_key || "unassigned") === familyKey) : classified;
  const groups = [...new Map(familyProducts.filter((product) => product.benchmark_group).map((product) => [product.benchmark_group || "", { key: product.benchmark_group || "", label: product.benchmarkCategory }])).values()]
    .sort((left, right) => ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(left.key) - ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(right.key));
  const groupProducts = groupKey ? familyProducts.filter((product) => product.benchmark_group === groupKey) : familyProducts;
  const ownProducts = groupProducts.filter(isOwn);
  const competitors = groupProducts.filter((product) => !isOwn(product));
  const productCard = (product: Product) => {
    const badge = statusBadge(product.status);
    return <button key={product.id} onClick={() => onDetail(product.id)} className="w-full rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">{product.brand}</p><p className="mt-0.5 text-sm font-semibold text-foreground">{product.name}</p>{product.configuration && <p className="mt-1 text-xs text-muted-foreground">Konfiguracja: {product.configuration}</p>}</div><span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.label}</span></div><p className="mt-3 text-xs text-muted-foreground">{product.benchmarkCategory}</p>{(product.zrodla !== null || product.coverage !== null) && <p className="mt-2 text-[11px] text-muted-foreground">{product.zrodla !== null ? `${product.zrodla} źródeł` : ""}{product.zrodla !== null && product.coverage !== null ? " · " : ""}{product.coverage !== null ? `coverage ${product.coverage}%` : ""}</p>}</button>;
  };
  return <div className="h-full overflow-auto bg-background"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-4"><div><h1 className="text-base font-semibold text-foreground">Produkty</h1><p className="mt-0.5 text-xs text-muted-foreground">Katalog według rodzin produktowych i grup benchmarkowych</p></div><button onClick={onResearch} className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"><Plus size={13} className="mr-1 inline" />Nowy research</button></header><main className="mx-auto max-w-6xl px-6 py-6"><div className="mb-5 flex flex-wrap items-center gap-3"><div className="relative min-w-64 flex-1"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Szukaj produktu..." className="w-full rounded border border-border bg-card py-2 pl-8 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary/30" /></div><label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={showUnassigned} onChange={(event) => { setShowUnassigned(event.target.checked); setFamilyKey(""); setGroupKey(""); }} />Pokaż nieprzypisane rekordy</label></div><nav aria-label="Breadcrumb" className="mb-6 flex items-center gap-1 text-xs text-muted-foreground"><button onClick={() => { setFamilyKey(""); setGroupKey(""); }} className={!familyKey ? "font-medium text-foreground" : "hover:text-primary"}>Produkty</button>{familyKey && <><ChevronRight size={12} /><button onClick={() => setGroupKey("")} className={!groupKey ? "font-medium text-foreground" : "hover:text-primary"}>{families.find((family) => family.key === familyKey)?.label || familyKey}</button></>}{groupKey && <><ChevronRight size={12} /><span className="font-medium text-foreground">{groups.find((group) => group.key === groupKey)?.label || groupKey}</span></>}</nav>{query.trim() ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Wyniki wyszukiwania</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{searchable.map((product) => <div key={product.id}>{productCard(product)}<p className="px-1 pt-1 text-[11px] text-muted-foreground">{familyLabel(product)} / {product.benchmarkCategory} · {isOwn(product) ? "Lionelo" : "Konkurent"}</p></div>)}</div>{searchable.length === 0 && <p className="rounded border border-dashed border-border p-6 text-sm text-muted-foreground">Brak sklasyfikowanych produktów spełniających wyszukiwanie.</p>}</section> : !familyKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Rodziny produktów</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{families.map((family) => { const items = classified.filter((product) => (product.subcategory_key || product.category_key || "unassigned") === family.key && product.benchmark_group); const own = items.filter(isOwn).length; const competition = items.length - own; const groupCount = new Set(items.map((product) => product.benchmark_group)).size; return <button key={family.key} onClick={() => setFamilyKey(family.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{family.label}</p><p className="mt-2 text-xs text-muted-foreground">{own} produktów Lionelo · {competition} konkurentów</p><p className="mt-1 text-xs text-muted-foreground">{groupCount} grupy benchmarkowe</p></button>; })}</div></section> : !groupKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Grupy benchmarkowe</h2><div className="grid gap-3 sm:grid-cols-2">{groups.map((group) => { const items = familyProducts.filter((product) => product.benchmark_group === group.key); const own = items.filter(isOwn).length; const competition = items.length - own; return <button key={group.key} onClick={() => setGroupKey(group.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{group.label}</p><p className="mt-2 text-xs text-muted-foreground">{own} Lionelo · {competition} konkurentów</p></button>; })}</div></section> : <section><h2 className="mb-3 text-sm font-semibold text-foreground">Produkty Lionelo ({ownProducts.length})</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{ownProducts.map(productCard)}</div><h2 className="mb-3 mt-8 text-sm font-semibold text-foreground">Konkurenci ({competitors.length})</h2>{competitors.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{competitors.map(productCard)}</div> : <p className="rounded border border-dashed border-border p-5 text-sm text-muted-foreground">Nie dodano jeszcze konkurentów do tej grupy.</p>}</section>}</main></div>;
}

function PageProduktyPrevious({ onDetail, onResearch }: { onDetail: (id: string) => void; onResearch: () => void }) {
  const { products } = useCatalog();
  const [query, setQuery] = useState("");
  const [showTests, setShowTests] = useState(false);
  const [categoryKey, setCategoryKey] = useState("");
  const [subcategoryKey, setSubcategoryKey] = useState("");
  const [groupKey, setGroupKey] = useState("");
  const visible = products.filter((product) => showTests || product.scope === "production");
  const matching = query.trim()
    ? visible.filter((product) => `${product.brand} ${product.name} ${product.configuration || ""}`.toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl")))
    : [];
  const categoryProducts = categoryKey ? visible.filter((product) => product.category_key === categoryKey) : visible;
  const subcategoryProducts = subcategoryKey ? categoryProducts.filter((product) => product.subcategory_key === subcategoryKey) : categoryProducts;
  const groupProducts = groupKey ? subcategoryProducts.filter((product) => product.benchmark_group === groupKey) : subcategoryProducts;
  const categories = [...new Map(visible.map((product) => [product.category_key || product.category, { key: product.category_key || product.category, label: product.category }])).values()];
  const subcategories = [...new Map(categoryProducts.map((product) => [product.subcategory_key || product.benchmarkCategory, { key: product.subcategory_key || product.benchmarkCategory, label: product.subcategoryLabel || product.benchmarkCategory }])).values()];
  const groups = [...new Map(subcategoryProducts.map((product) => [product.benchmark_group || product.benchmarkCategory, { key: product.benchmark_group || product.benchmarkCategory, label: product.benchmarkCategory }])).values()]
    .sort((left, right) => ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(left.key) - ["light_stroller", "standard_stroller", "stroller_2in1", "stroller_3in1"].indexOf(right.key));
  const resetFrom = (level: "category" | "subcategory" | "group") => {
    if (level === "category") { setCategoryKey(""); setSubcategoryKey(""); setGroupKey(""); }
    if (level === "subcategory") { setSubcategoryKey(""); setGroupKey(""); }
    if (level === "group") setGroupKey("");
  };
  const path = [
    ["Produkty", () => resetFrom("category")],
    categoryKey && [categories.find((item) => item.key === categoryKey)?.label || categoryKey, () => resetFrom("subcategory")],
    subcategoryKey && [subcategories.find((item) => item.key === subcategoryKey)?.label || subcategoryKey, () => resetFrom("group")],
    groupKey && [groups.find((item) => item.key === groupKey)?.label || groupKey, () => undefined],
  ].filter(Boolean) as Array<[string, () => void]>;
  const productCard = (product: Product) => {
    const badge = statusBadge(product.status);
    return <button key={product.id} onClick={() => onDetail(product.id)} className="w-full rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/30">
      <div className="flex items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">{product.brand}</p><p className="mt-0.5 text-sm font-semibold text-foreground">{product.name}</p>{product.configuration && <p className="mt-1 text-xs text-muted-foreground">Konfiguracja: {product.configuration}</p>}</div><span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.label}</span></div>
      <p className="mt-3 text-xs text-muted-foreground">{product.benchmarkCategory}</p>
      {(product.zrodla !== null || product.coverage !== null) && <p className="mt-2 text-[11px] text-muted-foreground">{product.zrodla !== null ? `${product.zrodla} źródeł` : ""}{product.zrodla !== null && product.coverage !== null ? " · " : ""}{product.coverage !== null ? `coverage ${product.coverage}%` : ""}</p>}
    </button>;
  };
  return <div className="h-full overflow-auto bg-background">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-4"><div><h1 className="text-base font-semibold text-foreground">Produkty</h1><p className="mt-0.5 text-xs text-muted-foreground">Katalog produktów według kategorii i grup benchmarkowych</p></div><button onClick={onResearch} className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"><Plus size={13} className="mr-1 inline" />Nowy research</button></header>
    <main className="mx-auto max-w-6xl px-6 py-6">
      <div className="mb-5 flex flex-wrap items-center gap-3"><div className="relative min-w-64 flex-1"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Szukaj produktu..." className="w-full rounded border border-border bg-card py-2 pl-8 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary/30" /></div><label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={showTests} onChange={(event) => { setShowTests(event.target.checked); resetFrom("category"); }} />Pokaż produkty testowe</label></div>
      <nav aria-label="Breadcrumb" className="mb-6 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">{path.map(([label, callback], index) => <Fragment key={`${label}-${index}`}><button onClick={callback} className={index === path.length - 1 ? "font-medium text-foreground" : "hover:text-primary"}>{label}</button>{index < path.length - 1 && <ChevronRight size={12} />}</Fragment>)}</nav>
      {query.trim() ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Wyniki wyszukiwania</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{matching.map((product) => <div key={product.id}>{productCard(product)}<p className="px-1 pt-1 text-[11px] text-muted-foreground">{product.category} / {product.subcategoryLabel || "—"} / {product.benchmarkCategory}</p></div>)}</div>{matching.length === 0 && <p className="rounded border border-dashed border-border p-6 text-sm text-muted-foreground">Brak produktów spełniających wyszukiwanie.</p>}</section>
      : !categoryKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Kategorie</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{categories.map((category) => { const items = visible.filter((product) => product.category_key === category.key); const count = new Set(items.map((product) => product.subcategory_key)).size; return <button key={category.key} onClick={() => setCategoryKey(category.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{category.label}</p><p className="mt-2 text-xs text-muted-foreground">{items.length} produktów · {count} {count === 1 ? "podkategoria" : "podkategorii"}</p></button>; })}</div></section>
      : !subcategoryKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Podkategorie</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{subcategories.map((subcategory) => { const items = categoryProducts.filter((product) => product.subcategory_key === subcategory.key); return <button key={subcategory.key} onClick={() => setSubcategoryKey(subcategory.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{subcategory.label}</p><p className="mt-2 text-xs text-muted-foreground">{items.length} produktów</p></button>; })}</div></section>
      : !groupKey ? <section><h2 className="mb-3 text-sm font-semibold text-foreground">Grupy benchmarkowe</h2><div className="grid gap-3 sm:grid-cols-2">{groups.map((group) => { const count = subcategoryProducts.filter((product) => product.benchmark_group === group.key).length; return <button key={group.key} onClick={() => setGroupKey(group.key)} className="rounded-lg border border-border bg-card p-5 text-left hover:border-primary/40"><p className="text-sm font-semibold text-foreground">{group.label}</p><p className="mt-2 text-xs text-muted-foreground">{count} produktów</p></button>; })}</div></section>
      : <section><h2 className="mb-3 text-sm font-semibold text-foreground">Produkty</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{groupProducts.map(productCard)}</div></section>}
    </main>
  </div>;
}

function PageProduktyLegacy({ onDetail, onResearch }: { onDetail: (id: string) => void; onResearch: () => void }) {
  const { products } = useCatalog();
  const [query, setQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("wszystkie");
  const [filterBrand, setFilterBrand] = useState<string>("wszystkie");
  const [filterCategory, setFilterCategory] = useState<string>("wszystkie");
  const [filterBenchmarkCategory, setFilterBenchmarkCategory] = useState<string>("wszystkie");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showFilter, setShowFilter] = useState(false);

  const filtered = products.filter((p) => {
    const q = query.toLowerCase();
    const matchQ = p.name.toLowerCase().includes(q) || p.brand.toLowerCase().includes(q);
    const matchS = filterStatus === "wszystkie" || p.status === filterStatus;
    const matchBrand = filterBrand === "wszystkie" || p.brand === filterBrand;
    const matchCategory = filterCategory === "wszystkie" || p.category === filterCategory;
    const matchBenchmarkCategory = filterBenchmarkCategory === "wszystkie" || p.benchmarkCategory === filterBenchmarkCategory;
    return matchQ && matchS && matchBrand && matchCategory && matchBenchmarkCategory;
  });
  const brands = [...new Set(products.map((product) => product.brand))].sort((a, b) => a.localeCompare(b, "pl"));
  const categories = [...new Set(products.map((product) => product.category))].sort((a, b) => a.localeCompare(b, "pl"));
  const benchmarkCategories = [...new Set(products.map((product) => product.benchmarkCategory))].sort((a, b) => a.localeCompare(b, "pl"));
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
          <p className="text-xs text-muted-foreground mt-0.5">{products.length} produktów w katalogu</p>
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

// ─── Pages: Benchmarki i produkty rynkowe ─────────────────────────────────────
function MarketProductCard({ product, onDetail, onSources }: { product: Product; onDetail?: (slug: string) => void; onSources?: (slug: string) => void }) {
  const badge = statusBadge(product.status);
  return <article className="rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/30">
    <div className="flex items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">{product.brand}</p><h2 className="mt-0.5 text-sm font-semibold text-foreground">{product.name}</h2><p className="mt-1 text-[11px] text-muted-foreground">{product.benchmarkCategory || "Bez przypisanej grupy"}</p></div><span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.label}</span></div>
    <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground"><span>{product.coverage === null ? "Coverage: —" : `Coverage: ${product.coverage}%`}</span><span>{product.zrodla ?? 0} źródeł</span></div>
    <div className="mt-4 flex flex-wrap gap-3">{onDetail && <button onClick={() => onDetail(product.slug)} className="text-xs font-medium text-primary hover:underline">Otwórz szczegóły</button>}{onSources && <button onClick={() => onSources(product.slug)} className="text-xs font-medium text-muted-foreground hover:text-primary">Źródła</button>}</div>
  </article>;
}

function PageProduktyKonkurencji({ onDetail }: { onDetail: (slug: string) => void }) {
  const { products } = useCatalog();
  const [query, setQuery] = useState("");
  const marketProducts = products.filter((product) => !isLioneloProduct(product));
  const filtered = marketProducts.filter((product) => `${product.brand} ${product.name} ${product.configuration || ""}`.toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl")));
  return <div className="h-full overflow-auto bg-background"><header className="border-b border-border bg-card px-6 py-4"><h1 className="text-base font-semibold text-foreground">Produkty konkurencji</h1><p className="mt-0.5 text-xs text-muted-foreground">Produkty marek innych niż Lionelo, z zachowaniem statusu researchu i dowodów.</p></header><main className="mx-auto max-w-6xl px-6 py-6"><div className="relative mb-5"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Szukaj marki lub modelu..." className="w-full rounded border border-border bg-card py-2 pl-8 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary/30" /></div>{filtered.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{filtered.map((product) => <MarketProductCard key={product.slug} product={product} onDetail={onDetail} />)}</div> : <div className="rounded-lg border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">Brak produktów konkurencji spełniających kryteria.</div>}</main></div>;
}

function PageZrodlaIndex({ onSources }: { onSources: (slug: string) => void }) {
  const { products } = useCatalog();
  const productsWithSources = products.filter((product) => (product.zrodla || 0) > 0);
  return <div className="h-full overflow-auto bg-background"><header className="border-b border-border bg-card px-6 py-4"><h1 className="text-base font-semibold text-foreground">Źródła</h1><p className="mt-0.5 text-xs text-muted-foreground">Przejdź do aukcji, snapshotów i dowodów przypisanych do produktu.</p></header><main className="mx-auto max-w-6xl px-6 py-6">{productsWithSources.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{productsWithSources.map((product) => <MarketProductCard key={product.slug} product={product} onSources={onSources} />)}</div> : <div className="rounded-lg border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">Brak produktów z zapisanymi źródłami.</div>}</main></div>;
}

function InternalBenchmarkComparison({ groupKey, onBack }: { groupKey: string; onBack: () => void }) {
  const { products } = useCatalog();
  const [detail, setDetail] = useState<InternalBenchmarkDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; setDetail(null); setError(""); void apiRequest<InternalBenchmarkDetail>(`/internal-benchmarks/${encodeURIComponent(groupKey)}`).then((response) => { if (active) setDetail(response); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Nie udało się wczytać benchmarku wewnętrznego."); }); return () => { active = false; }; }, [groupKey]);
  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  if (!detail) return <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">Wczytywanie grupy benchmarkowej…</div>;
  const slugs = detail.participants.map((participant) => participant.product_slug);
  const anchor = products.find((product) => product.slug === slugs[0]);
  return <div><button onClick={onBack} className="mb-4 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"><ArrowLeft size={13} />Wróć do grup</button><div className="mb-5"><h2 className="text-base font-semibold text-foreground">{detail.title}</h2><p className="mt-1 text-xs text-muted-foreground">{detail.participant_count} produktów Lionelo w tej grupie.</p></div>{anchor ? <ProductBenchmarkPanel product={anchor} initialSelection={slugs} allowedProductSlugs={slugs} /> : <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">Brak produktu z tej grupy w lokalnym katalogu.</div>}</div>;
}

function PageBenchmarki({ onDetail }: { onDetail: (slug: string) => void }) {
  const { products } = useCatalog();
  const [tab, setTab] = useState<"internal" | "competitive">("internal");
  const [internal, setInternal] = useState<InternalBenchmarkSummary[]>([]);
  const [competitive, setCompetitive] = useState<CompetitiveBenchmarkSummary[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let active = true; setError(""); void Promise.all([apiRequest<InternalBenchmarkSummary[]>("/internal-benchmarks"), apiRequest<CompetitiveBenchmarkSummary[]>("/benchmarks")]).then(([internalGroups, competitiveBenchmarks]) => { if (!active) return; setInternal(internalGroups); setCompetitive(competitiveBenchmarks); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Nie udało się wczytać benchmarków."); }); return () => { active = false; }; }, []);
  const anchorFor = (benchmark: CompetitiveBenchmarkSummary) => products.find((product) => product.productId === benchmark.anchor_product_id);
  return <div className="h-full overflow-auto bg-background"><header className="border-b border-border bg-card px-6 py-4"><h1 className="text-base font-semibold text-foreground">Benchmarki</h1><p className="mt-0.5 text-xs text-muted-foreground">Porównania produktów Lionelo oraz zapisane benchmarki konkurencyjne.</p><div className="mt-4 flex gap-1 border-b border-border -mb-4"><button onClick={() => { setTab("internal"); setSelectedGroup(""); }} className={`border-b-2 px-3 py-2 text-xs font-medium ${tab === "internal" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Wewnętrzne</button><button onClick={() => { setTab("competitive"); setSelectedGroup(""); }} className={`border-b-2 px-3 py-2 text-xs font-medium ${tab === "competitive" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Konkurencyjne</button></div></header><main className="mx-auto max-w-6xl px-6 py-6">{error ? <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : tab === "internal" && selectedGroup ? <InternalBenchmarkComparison groupKey={selectedGroup} onBack={() => setSelectedGroup("")} /> : tab === "internal" ? <div className="grid gap-3 sm:grid-cols-2">{internal.map((group) => <button key={group.benchmark_group_key} onClick={() => setSelectedGroup(group.benchmark_group_key)} className="rounded-lg border border-border bg-card p-5 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"><p className="text-sm font-semibold text-foreground">{group.benchmark_group_label}</p><p className="mt-2 text-xs text-muted-foreground">{group.participant_count} produktów Lionelo</p></button>)}</div> : competitive.length ? <div className="space-y-3">{competitive.map((benchmark) => { const anchor = anchorFor(benchmark); return <article key={benchmark.benchmark_id} className="rounded-lg border border-border bg-card p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-semibold text-foreground">{benchmark.title}</h2><p className="mt-1 text-xs text-muted-foreground">{anchor ? `${anchor.brand} ${anchor.name}` : "Produkt Lionelo"} · {benchmark.benchmark_group_key} · {benchmark.participant_count} produktów rynkowych</p></div><span className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground">{benchmark.status}</span></div>{anchor && <button onClick={() => onDetail(anchor.slug)} className="mt-3 text-xs font-medium text-primary hover:underline">Otwórz produkt Lionelo</button>}</article>; })}</div> : <div className="rounded-lg border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">Brak zapisanych benchmarków konkurencyjnych.</div>}</main></div>;
}

// ─── Page: Produkt — Szczegóły ────────────────────────────────────────────────
function ProductBenchmarkPanel({ product, initialSelection = [], allowedProductSlugs }: { product: Product; initialSelection?: string[]; allowedProductSlugs?: string[] }) {
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
        const candidates = response.models.filter((model) => !allowedProductSlugs || allowedProductSlugs.includes(model.slug));
        const requested = initialSelection.filter((slug) => candidates.some((model) => model.slug === slug));
        const initial = requested.length >= 2 ? requested : candidates.slice(0, 5).map((model) => model.slug);
        if (initial.includes(product.slug)) setSelected(new Set(initial));
      })
      .catch((requestError) => active && setError(requestError instanceof Error ? requestError.message : "Nie udało się wczytać benchmarku kategorii."));
    return () => { active = false; };
  }, [product.slug, initialSelection, allowedProductSlugs]);

  const toggle = (slug: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(slug)) next.delete(slug);
    else if (next.size < 5) next.add(slug);
    return next.size ? next : new Set([product.slug]);
  });
  const availableModels = (data?.models || []).filter((model) => !allowedProductSlugs || allowedProductSlugs.includes(model.slug));
  const models = availableModels.filter((model) => selected.has(model.slug));
  const rows = (data?.fields || []).filter((field) => {
    if (!onlyDifferences) return true;
    const values = models.map((model) => model.values[field]?.value || "X");
    return new Set(values).size > 1;
  });

  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  if (!data) return <div className="rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">Wczytywanie benchmarku kategorii…</div>;
  if (!data.has_comparison) return <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center"><GitCompare size={24} className="mx-auto text-muted-foreground" /><p className="mt-3 text-sm font-medium text-foreground">Brak innych przeanalizowanych produktów w tej kategorii.</p><p className="mt-1 text-xs text-muted-foreground">Gdy kolejny produkt z kategorii „{data.benchmark_category || "tej"}” zostanie przeanalizowany, pojawi się tutaj porównanie.</p></div>;

  return <section className="rounded-lg border border-border bg-card p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-semibold text-foreground">Porównanie w kategorii: {data.benchmark_category}</h2><p className="mt-1 text-xs text-muted-foreground">Wybierz od 2 do 5 produktów. Ten widok porównuje modele, nie powiela karty pojedynczego produktu.</p></div><label className="inline-flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={onlyDifferences} onChange={(event) => setOnlyDifferences(event.target.checked)} />Tylko różnice</label></div><div className="mt-4 flex flex-wrap gap-2">{availableModels.map((model) => <label key={model.slug} className={`inline-flex cursor-pointer items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs ${selected.has(model.slug) ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground"}`}><input className="sr-only" type="checkbox" checked={selected.has(model.slug)} onChange={() => toggle(model.slug)} /><span>{model.brand} {model.model}</span><span className="text-[10px] opacity-70">{model.coverage ?? "—"}%</span></label>)}</div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-xs"><thead><tr className="border-b border-border text-left text-muted-foreground"><th className="sticky left-0 z-10 bg-card px-2 py-2 font-medium">Parametr</th>{models.map((model) => <th key={model.slug} className="min-w-44 px-2 py-2 font-medium">{model.brand} {model.model}</th>)}</tr></thead><tbody>{rows.map((field) => <tr key={field} className="border-b border-border last:border-0 align-top"><td className="sticky left-0 z-10 bg-card px-2 py-2.5 font-medium text-foreground">{field}</td>{models.map((model) => { const value = model.values[field]?.value || "X"; const different = models.some((other) => (other.values[field]?.value || "X") !== value); return <td key={model.slug} className={`px-2 py-2.5 ${different ? "bg-amber-50/50" : ""} ${value === "X" ? "text-muted-foreground" : "text-foreground"}`}>{value === "X" ? "Brak danych" : value}</td>; })}</tr>)}</tbody></table></div></section>;
}

type ProductProfile = {
  profile_status: string; one_sentence_summary: string; narrative_summary: string;
  discovered_themes: Array<{ theme_id: string; title: string; summary: string; confidence: string; supporting_source_ids: string[]; supporting_evidence_ids: string[]; supporting_visual_block_ids: string[]; supporting_media_ids: string[] }>;
  factual_highlights: Array<{ statement: string; supporting_evidence_ids: string[] }>;
  marketplace_narrative: Array<{ observation: string; confidence: string; supporting_source_ids: string[] }>;
  visual_positioning: Array<{ observation: string; confidence: string; supporting_source_ids: string[]; supporting_visual_block_ids: string[]; supporting_media_ids: string[]; visual_access: string }>;
  important_conflicts: Array<{ summary: string; supporting_source_ids: string[]; supporting_evidence_ids: string[] }>;
  important_unknowns: Array<{ summary: string; related_source_ids: string[] }>;
  input_summary: { textual_coverage?: string; visual_coverage?: string; sources_used?: number; visual_blocks_used?: number };
  generation: { generated_at?: string; model_name?: string; failure_reason?: string; latest_failure_reason?: string; latest_failure_code?: string; latest_attempt_at?: string };
};

function ProductProfilePanel({ product, refreshToken = 0 }: { product: Product; refreshToken?: number }) {
  const [profile, setProfile] = useState<ProductProfile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [profileEnabled, setProfileEnabled] = useState(false);
  useEffect(() => { void apiRequest<{ ai_enabled?: boolean }>("/product-profile/capabilities").then((capabilities) => setProfileEnabled(Boolean(capabilities.ai_enabled))).catch(() => setProfileEnabled(false)); }, []);
  useEffect(() => { let active = true; setLoading(true); setError(""); void apiRequest<ProductProfile>(`/products/${product.slug}/profile`).then((value) => { if (active) setProfile(value); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Nie udało się wczytać profilu."); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [product.slug, refreshToken]);
  if (loading) return <div className="rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">Wczytywanie profilu produktu…</div>;
  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  const regenerate = async () => { setGenerating(true); setError(""); try { setProfile(await apiRequest<ProductProfile>(`/products/${product.slug}/profile/generate`, { method: "POST" })); } catch (reason) { setError(reason instanceof Error ? reason.message : "Nie udało się uruchomić generowania profilu."); } finally { setGenerating(false); } };
  const statusLabel: Record<string, string> = { not_generated: "Nie wygenerowano", generating: "Generowanie", generated: "Gotowy", partial: "Częściowy", stale: "Nieaktualny", failed: "Błąd" };
  const references = (ids: string[] = []) => ids.length ? <div className="mt-2 flex flex-wrap gap-1">{ids.map((id) => <span key={id} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground" title="Odwołanie jest zapisane w profilu, ale ten typ nie ma jeszcze osobnego widoku.">{id}</span>)}</div> : null;
  if (!profile || profile.profile_status === "not_generated") { const reason = profile?.generation?.failure_reason || profile?.generation?.latest_failure_reason || "Brak wystarczających danych źródłowych do wygenerowania profilu."; return <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center"><FileText size={24} className="mx-auto text-muted-foreground" /><p className="mt-3 text-sm font-medium text-foreground">Profil produktu nie został jeszcze wygenerowany.</p><p className="mt-1 text-xs text-muted-foreground">{reason}</p>{profileEnabled && <button onClick={() => void regenerate()} disabled={generating} className="mt-4 rounded border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted">Wygeneruj profil</button>}</div>; }
  if (profile.profile_status === "failed") return <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800"><p className="font-medium">Generowanie profilu zakończyło się błędem.</p><p className="mt-1 text-xs">{profile.generation.latest_failure_reason || profile.generation.failure_reason || "Brak szczegółu błędu."}</p>{profileEnabled && <button onClick={() => void regenerate()} disabled={generating} className="mt-3 rounded border border-red-300 px-3 py-1.5 text-xs font-medium">Spróbuj ponownie</button>}</div>;
  const section = (title: string, rows: Array<{ title?: string; body?: string; ids?: string[] }>) => rows.length ? <section className="rounded-lg border border-border bg-card p-4"><h2 className="text-sm font-semibold text-foreground">{title}</h2><div className="mt-3 space-y-2">{rows.map((row, index) => <div key={`${title}-${index}`} className="rounded border border-border bg-muted/20 p-3 text-xs"><p className="font-medium text-foreground">{row.title || row.body}</p>{row.title && row.body && <p className="mt-1 text-muted-foreground leading-relaxed">{row.body}</p>}{references(row.ids)}</div>)}</div></section> : null;
  return <div className="flex-1 overflow-auto px-6 py-5 space-y-4">
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-base font-semibold text-foreground">Profil produktu</h2>{profile.profile_status === "stale" ? <p className="mt-1 text-sm text-amber-700">Profil jest nieaktualny i nie jest prezentowany jako bieżący wynik.</p> : <p className="mt-1 text-sm text-muted-foreground">{profile.one_sentence_summary}</p>}</div>
        <div className="flex items-center gap-2"><span className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground">{statusLabel[profile.profile_status] || profile.profile_status}</span>{profileEnabled && <button onClick={() => void regenerate()} disabled={generating} className="rounded border border-border px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50">{generating ? "Generowanie…" : "Wygeneruj ponownie"}</button>}</div>
      </div>
      {profile.profile_status !== "stale" && profile.narrative_summary && <p className="mt-4 max-w-3xl text-sm leading-relaxed text-foreground">{profile.narrative_summary}</p>}
      <p className="mt-3 text-xs text-muted-foreground">Pokrycie tekstowe: {profile.input_summary.textual_coverage || "—"} · wizualne: {profile.input_summary.visual_coverage || "—"} · źródła: {profile.input_summary.sources_used ?? 0} · bloki wizualne: {profile.input_summary.visual_blocks_used ?? 0}</p>
    </section>
    {profile.profile_status !== "stale" && <>
      {section("Najważniejsze fakty", profile.factual_highlights.map((x) => ({ body: x.statement, ids: x.supporting_evidence_ids })))}
      {section("Odkryte tematy", profile.discovered_themes.map((x) => ({ title: x.title, body: x.summary, ids: [...x.supporting_source_ids, ...x.supporting_evidence_ids, ...x.supporting_visual_block_ids, ...x.supporting_media_ids] })))}
      {section("Opis w ofertach", profile.marketplace_narrative.map((x) => ({ body: x.observation, ids: x.supporting_source_ids })))}
      {section("Kontekst wizualny", profile.visual_positioning.map((x) => ({ body: x.observation, ids: [...x.supporting_source_ids, ...x.supporting_visual_block_ids, ...x.supporting_media_ids] })))}
      {section("Istotne konflikty", profile.important_conflicts.map((x) => ({ body: x.summary, ids: [...x.supporting_source_ids, ...x.supporting_evidence_ids] })))}
      {section("Otwarte kwestie", profile.important_unknowns.map((x) => ({ body: x.summary, ids: x.related_source_ids })))}
    </>}
    <p className="text-xs text-muted-foreground">Profil utworzony: {profile.generation.generated_at ? new Date(profile.generation.generated_at).toLocaleString("pl-PL") : "—"} · model: {profile.generation.model_name || "—"}</p>
  </div>;
}

function PageProduktSzczegoly({ productId, onBack, backLabel, onResearch, onSources, comparisonSelection = [] }: { productId: string; onBack: () => void; backLabel: string; onResearch: () => void; onSources: () => void; comparisonSelection?: string[] }) {
  const { products } = useCatalog();
  const p = products.find((x) => x.id === productId) || null;
  if (!p) return <div className="p-6 text-sm text-muted-foreground">Nie znaleziono produktu w katalogu.</div>;
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
  const [activeTab, setActiveTab] = useState<"product" | "profile" | "benchmark" | "history">("product");
  const [fieldFilter, setFieldFilter] = useState<"all" | "valid" | "weak" | "conflicting" | "missing" | "legacy">("all");
  const [analysisMode, setAnalysisMode] = useState<"saved" | "refresh">("saved");
  const [productRefreshToken, setProductRefreshToken] = useState(0);
  useEffect(() => {
    if (comparisonSelection.includes(p.slug)) setActiveTab("benchmark");
  }, [comparisonSelection, p.slug]);
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
    if (!refreshRun || !isRunActive(refreshRun)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await apiRequest<ApiRun>(`/runs/${refreshRun.run_id}`);
        setRefreshRun(latest);
        if (!isRunActive(latest)) {
          if (shouldAutoReloadAfterRun(latest)) {
            window.setTimeout(() => window.location.reload(), 250);
          } else if (isRunFailure(latest)) {
            setRefreshError(latest.error || "Proces zakończył się błędem. Dane produktu nie zostały automatycznie odświeżone.");
          }
        }
      } catch (error) {
        setRefreshError(error instanceof Error ? error.message : "Utracono połączenie z lokalnym API.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refreshRun?.run_id, refreshRun?.status]);

  useEffect(() => {
    if (!refreshRun || isRunActive(refreshRun)) return;
    if (shouldAutoReloadAfterRun(refreshRun)) {
      const timer = window.setTimeout(() => window.location.reload(), 250);
      return () => window.clearTimeout(timer);
    }
    if (isRunFailure(refreshRun)) {
      setRefreshError(refreshRun.error || "Proces zakończył się błędem. Dane produktu nie zostały automatycznie odświeżone.");
    }
  }, [refreshRun]);

  const analysisRunLabel = (run: ApiRun) => isRunPartial(run)
    ? "Analiza częściowa"
    : isRunSuccess(run)
      ? "Analiza zakończona"
      : isRunFailure(run)
        ? "Analiza zatrzymana"
        : "Analiza w toku";
  const refreshRunFailed = refreshRun ? isRunFailure(refreshRun) : false;
  const refreshRunPartial = refreshRun ? isRunPartial(refreshRun) : false;
  const refreshRunSucceeded = refreshRun ? isRunSuccess(refreshRun) : false;

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
            {backLabel}
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
            <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-medium ${statusBadge(p.status).cls}`}>{statusBadge(p.status).label}</span>
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
          <button role="tab" aria-selected={activeTab === "profile"} onClick={() => setActiveTab("profile")} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "profile" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Profil produktu</button>
          <button role="tab" aria-selected={activeTab === "benchmark"} onClick={() => setActiveTab("benchmark")} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "benchmark" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Benchmark</button>
          <button role="tab" aria-selected={false} onClick={onSources} className="px-3 py-2 text-xs font-medium border-b-2 border-transparent text-muted-foreground hover:text-foreground transition-colors">Aukcje i źródła</button>
          <button role="tab" aria-selected={activeTab === "history"} onClick={() => { setActiveTab("history"); void loadHistory(); }} className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "history" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Historia</button>
        </div>
      </div>

      {activeTab === "history" ? <div className="flex-1 overflow-auto px-6 py-5 space-y-4"><section className="max-w-3xl bg-card border border-border rounded-lg p-4"><div className="flex items-center justify-between gap-2"><h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Clock size={14} className="text-muted-foreground" />Historia produktu</h2><button onClick={() => void loadHistory()} className="text-xs text-primary hover:underline">Odśwież listę</button></div>{analysisRuns.length > 0 && <div className="mt-4"><p className="text-xs font-medium text-foreground">Uruchomienia analizy</p><div className="mt-2 space-y-2">{analysisRuns.map((run) => <div key={run.run_id} className="rounded border border-border bg-muted/20 p-3 text-xs"><p className="font-medium text-foreground">{analysisRunLabel(run)}</p><p className="mt-1 text-muted-foreground">{run.started_at ? new Date(run.started_at).toLocaleString("pl-PL") : "—"} · użyte źródła: {run.analysis?.used_sources?.length ?? 0}</p></div>)}</div></div>}</section></div> : activeTab === "profile" ? <ProductProfilePanel product={p} refreshToken={productRefreshToken} /> : activeTab === "benchmark" ? <div className="flex-1 overflow-auto px-6 py-5"><ProductBenchmarkPanel product={p} initialSelection={comparisonSelection} /></div> : (
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
            })}</tbody></table></div></> : <div className="flex items-start gap-2 p-3 bg-muted/30 rounded text-xs text-muted-foreground"><Clock size={13} className="mt-0.5 flex-shrink-0" /><div><p className="font-medium text-foreground">Produkt dodany</p><p className="mt-1">Brak zakończonego researchu. Uruchom wyszukiwanie źródeł w Research albo wybierz „Odśwież dane”.</p></div></div>}
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
      {refreshRun && <div className={`fixed right-5 bottom-5 z-40 w-[min(420px,calc(100vw-2.5rem))] rounded-lg border bg-card p-4 shadow-lg ${refreshRunFailed ? "border-red-200" : refreshRunPartial ? "border-amber-200" : refreshRunSucceeded ? "border-emerald-200" : "border-border"}`}><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold text-foreground">{refreshRun.analysis ? "Analiza zapisanych danych" : "Odświeżanie danych"}</p><span className="text-[11px] text-muted-foreground">{refreshRun.progress}%</span></div><p className="mt-1 text-xs text-muted-foreground">{refreshRun.current_step}</p>{refreshRun.logs_tail[refreshRun.logs_tail.length - 1] && <p className="mt-2 rounded bg-muted/40 p-2 text-[11px] text-muted-foreground">Ostatni log: {refreshRun.logs_tail[refreshRun.logs_tail.length - 1]}</p>}<div className="mt-3 h-1.5 overflow-hidden rounded bg-muted"><div className="h-full rounded bg-primary transition-all" style={{ width: `${refreshRun.progress}%` }} /></div>{refreshRunSucceeded && <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">{refreshRun.analysis ? <><span>Użyte źródła: {refreshRun.analysis.used_sources?.length ?? 0}</span><span>Zmienione pola: {refreshRun.analysis.fields_changed ?? 0}</span><span>Coverage: {refreshRun.analysis.coverage_before ?? "—"}% → {refreshRun.analysis.coverage_after ?? "—"}%</span></> : <><span>Nowe źródła: {refreshRun.refresh?.new_sources ?? 0}</span><span>Niedostępne: {refreshRun.refresh?.unavailable_sources ?? 0}</span><span>Zmienione pola: {refreshRun.refresh?.fields_changed ?? 0}</span><span>Coverage: {refreshRun.refresh?.coverage_before ?? "—"}% → {refreshRun.refresh?.coverage_after ?? "—"}%</span></>}<span>Profil: {refreshRun.product_profile_status || "—"}</span></div>}{refreshRun.product_profile_warning && <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-800">Profil produktu: {refreshRun.product_profile_warning}</p>}{refreshRunFailed && <><p className="mt-3 text-xs text-red-700">{refreshRun.error}</p><details className="mt-3 text-[11px] text-muted-foreground"><summary className="cursor-pointer">Dziennik techniczny</summary><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap">{refreshRun.logs_tail.join("\n")}</pre></details></>}<button onClick={() => setRefreshRun(null)} className="mt-3 text-[11px] text-primary hover:underline">Zamknij</button></div>}
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

function VisualSourcePanel({ source, snapshot, blocks, media, loading, onClose }: { source: ProductSource; snapshot: VisualSnapshot | null; blocks: VisualBlock[]; media: VisualMedia[]; loading: boolean; onClose: () => void }) {
  const [region, setRegion] = useState("all");
  const [contextBlock, setContextBlock] = useState<VisualBlock | null>(null);
  const apiBase = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api").replace(/\/api$/, "").replace(/\/$/, "");
  const visible = blocks.filter((block) => region === "all" || block.region === region);
  const mediaFor = (block: VisualBlock) => media.filter((item) => block.media_ids.includes(item.media_id));
  const imageUrl = (item: VisualMedia) => item.original_url || "";
  return <aside className="fixed right-0 top-0 z-50 flex h-full w-[min(680px,100vw)] flex-col border-l border-border bg-card shadow-2xl"><div className="flex items-start justify-between gap-3 border-b border-border p-4"><div className="min-w-0"><p className="text-[11px] text-muted-foreground">Widok źródła</p><h2 className="mt-1 text-sm font-semibold text-foreground break-words">{source.title}</h2><p className="mt-1 text-[11px] text-muted-foreground">{snapshot?.capture_status === "captured" ? "Wizualny snapshot zapisany" : "Kontekst z lokalnego HTML; brak pełnego screenshotu renderu."}</p></div><button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Zamknij panel"><X size={16} /></button></div>{loading ? <p className="p-5 text-sm text-muted-foreground">Wczytywanie widoku źródła…</p> : !snapshot ? <p className="p-5 text-sm text-muted-foreground">Nie zapisano jeszcze kontekstu wizualnego dla tego źródła.</p> : <div className="min-h-0 flex-1 overflow-auto p-4"><div className="rounded border border-border bg-muted/20 p-3 text-xs"><p className="font-medium text-foreground">Status: {snapshot.capture_status === "captured" ? "pełny snapshot" : "częściowy kontekst"}</p><p className="mt-1 text-muted-foreground">Bloki: {snapshot.blocks_count} · media: {snapshot.media_count} · provider: {snapshot.capture_provider}</p>{snapshot.full_page_artifact_id ? <a className="mt-2 inline-flex text-primary hover:underline" href={`${apiBase}/api/visual-artifacts/${snapshot.full_page_artifact_id}`} target="_blank" rel="noreferrer">Otwórz pełny screenshot</a> : <p className="mt-2 text-muted-foreground">Brak pełnego screenshotu: nie został wykonany drugi request tylko dla wizualizacji.</p>}</div><div className="mt-4 flex flex-wrap gap-1.5">{[["all", "Wszystkie"], ["gallery", "Galeria"], ["feature", "Funkcje"], ["dimensions", "Wymiary"], ["included", "Zestaw"], ["accessory", "Akcesoria"], ["variant", "Warianty"]].map(([key, label]) => <button key={key} onClick={() => setRegion(key)} className={`rounded-full border px-2.5 py-1 text-[11px] ${region === key ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground hover:bg-muted"}`}>{label}</button>)}</div><div className="mt-4 space-y-3">{visible.length === 0 ? <p className="rounded border border-dashed border-border p-4 text-xs text-muted-foreground">Brak bloków dla wybranego filtra.</p> : visible.map((block) => <article key={block.block_id} className="rounded-lg border border-border bg-card p-3"><div className="flex items-start justify-between gap-3"><div><span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{block.region}</span><h3 className="mt-2 text-xs font-semibold text-foreground">{block.heading || "Fragment źródła"}</h3></div><button onClick={() => setContextBlock(block)} className="text-[11px] text-primary hover:underline">Pokaż w kontekście</button></div><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{block.body_text || "Brak tekstowego opisu w tym samym kontenerze DOM."}</p><div className="mt-3 flex flex-wrap gap-2">{mediaFor(block).map((item) => item.media_type === "image" && imageUrl(item) ? <a key={item.media_id} href={imageUrl(item)} target="_blank" rel="noreferrer" className="block h-16 w-16 overflow-hidden rounded border border-border bg-muted"><img src={imageUrl(item)} alt={item.alt_text || block.heading || "Medium źródła"} className="h-full w-full object-cover" /></a> : <a key={item.media_id} href={imageUrl(item)} target="_blank" rel="noreferrer" className="rounded border border-border bg-muted/30 px-2 py-1 text-[10px] text-muted-foreground">{item.media_type === "video" ? "Wideo / animacja" : "Medium"}</a>)}</div></article>)}</div>{contextBlock && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"><div className="w-full max-w-xl rounded-lg border border-border bg-card p-4 shadow-xl"><div className="flex items-start justify-between gap-3"><div><p className="text-[11px] text-muted-foreground">Kontekst bloku</p><h3 className="text-sm font-semibold text-foreground">{contextBlock.heading || "Fragment źródła"}</h3></div><button onClick={() => setContextBlock(null)} className="rounded p-1 hover:bg-muted"><X size={15} /></button></div>{contextBlock.section_artifact_id ? <img className="mt-3 max-h-[55vh] w-full rounded object-contain" src={`${apiBase}/api/visual-artifacts/${contextBlock.section_artifact_id}`} alt={contextBlock.heading || "Crop sekcji"} /> : <div className="mt-3 rounded border border-dashed border-border bg-muted/20 p-4 text-xs text-muted-foreground">Crop sekcji nie jest dostępny, bo lokalny HTML nie zawiera wiarygodnego bounding boxa z tego samego renderu.</div>}<p className="mt-3 text-xs leading-relaxed text-foreground">{contextBlock.body_text || "Brak opisu w bloku."}</p>{source.original_url && <a href={source.original_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex text-xs text-primary hover:underline">Otwórz źródło</a>}</div></div>}</div>}</aside>;
}

function PageProduktZrodla({ productId, onBack }: { productId: string; onBack: () => void }) {
  const { products } = useCatalog();
  const product = products.find((item) => item.id === productId) || null;
  if (!product) return <div className="p-6 text-sm text-muted-foreground">Nie znaleziono produktu w katalogu.</div>;
  const [data, setData] = useState<ProductSourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | ProductSource["role"] | "unavailable">("all");
  const [selectedSource, setSelectedSource] = useState<ProductSource | null>(null);
  const [snapshot, setSnapshot] = useState<SourceSnapshotResponse | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [contribution, setContribution] = useState<SourceContributionResponse | null>(null);
  const [contributionLoading, setContributionLoading] = useState(false);
  const [visualSnapshot, setVisualSnapshot] = useState<VisualSnapshot | null>(null);
  const [visualBlocks, setVisualBlocks] = useState<VisualBlock[]>([]);
  const [visualMedia, setVisualMedia] = useState<VisualMedia[]>([]);
  const [visualLoading, setVisualLoading] = useState(false);

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

  const openVisual = async (source: ProductSource) => {
    setSelectedSource(source);
    setSnapshot(null);
    setContribution(null);
    setVisualSnapshot(null);
    setVisualBlocks([]);
    setVisualMedia([]);
    setVisualLoading(true);
    try {
      const encoded = encodeURIComponent(source.source_id);
      const [visuals, blocks, media] = await Promise.all([
        apiRequest<VisualEnvelope>(`/sources/${encoded}/visuals`),
        apiRequest<VisualPage<VisualBlock>>(`/sources/${encoded}/visual-blocks?limit=120`),
        apiRequest<VisualPage<VisualMedia>>(`/sources/${encoded}/media?limit=160`),
      ]);
      setVisualSnapshot(visuals.snapshot);
      setVisualBlocks(blocks.items);
      setVisualMedia(media.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Nie udało się wczytać widoku źródła.");
    } finally {
      setVisualLoading(false);
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
    return <article className="rounded-lg border border-border bg-card p-4 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-1.5"><span className="text-[11px] font-medium text-primary">{roleLabel(source.role)}</span><span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${status.cls}`}>{status.label}</span></div><h3 className="mt-1.5 text-sm font-semibold text-foreground break-words">{source.title}</h3><p className="mt-1 text-[11px] text-muted-foreground">{source.marketplace === "manufacturer" ? "Oficjalne źródło producenta" : "Aukcja marketplace"} · {source.domain || "brak domeny"}</p></div><div className="flex flex-wrap gap-2"><button onClick={() => void openVisual(source)} className="rounded border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted">Widok źródła</button><button onClick={() => void openContribution(source)} className="rounded border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted">Pokaż wkład źródła</button>{source.snapshot_available ? <button onClick={() => void openSnapshot(source)} className="rounded border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted">Otwórz snapshot</button> : <span className="rounded border border-border px-2.5 py-1.5 text-[11px] text-muted-foreground">Brak snapshotu</span>}{source.original_url ? <a href={source.original_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded bg-primary px-2.5 py-1.5 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"><ExternalLink size={12} />Otwórz aukcję</a> : <span className="rounded bg-muted px-2.5 py-1.5 text-[11px] text-muted-foreground">Brak URL</span>}</div></div><div className="mt-3 flex flex-wrap gap-1.5">{checks.map(([label, complete]) => <span key={String(label)} className={`rounded border px-1.5 py-0.5 text-[10px] ${complete ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-border bg-muted text-muted-foreground"}`}>{complete ? "✓" : "—"} {label}</span>)}</div><div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4"><div className="rounded bg-muted/30 p-2">Nowe pola: <b>{contributionSummary?.unique_fields_contributed.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Potwierdzenia: <b>{contributionSummary?.confirmed_fields.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Konflikty: <b>{contributionSummary?.conflicting_fields.length ?? 0}</b></div><div className="rounded bg-muted/30 p-2">Finalnie użyte: <b>{contributionSummary?.final_fields_used.length ?? 0}</b></div></div><div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[11px] sm:grid-cols-3 xl:grid-cols-5"><div><p className="text-muted-foreground">ID oferty</p><p className="mt-0.5 font-mono text-foreground break-all">{source.offer_id || "—"}</p></div><div><p className="text-muted-foreground">Cena</p><p className="mt-0.5 text-foreground">{source.price || "—"}</p></div><div><p className="text-muted-foreground">Sprzedawca</p><p className="mt-0.5 text-foreground break-words">{source.seller.name || "—"}{source.seller.rating ? ` · ${source.seller.rating}` : ""}</p></div><div><p className="text-muted-foreground">Stan pobrania</p><p className="mt-0.5 text-foreground">{fetchStatus(source.fetch_status)} · {cleanerStatus(source.cleaner_status)}</p></div><div><p className="text-muted-foreground">Wartość źródła</p><p className="mt-0.5 text-foreground">{source.offer_quality.score ?? "—"}{source.offer_quality.score !== null ? "/100" : ""}</p></div></div>{source.fetch_error && <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-[11px] text-red-700">Błąd pobrania: {source.fetch_error}</p>}<div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground"><span>Źródło: <span className="font-mono text-foreground">{source.source_id}</span></span><span>Pierwsze pobranie: {source.first_fetched_at ? new Date(source.first_fetched_at).toLocaleString("pl-PL") : "—"}</span><span>Ostatnie pobranie: {source.last_fetched_at ? new Date(source.last_fetched_at).toLocaleString("pl-PL") : "—"}</span></div></article>;
  };

  return <div className="h-full overflow-auto"><div className="border-b border-border bg-card px-6 py-4"><div className="flex items-center gap-1.5 text-xs text-muted-foreground"><button onClick={onBack} className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft size={11} />{product.brand} {product.name}</button><ChevronRight size={11} /><span className="font-medium text-foreground">Aukcje i źródła</span></div><div className="mt-3 flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-base font-semibold text-foreground">Aukcje i źródła: {product.brand} {product.name}</h1><p className="mt-1 text-xs text-muted-foreground">Każda wybrana oferta jest rozliczona niezależnie od powodzenia pobrania i przypięcia do benchmarku.</p></div><button onClick={() => void loadSources()} className="inline-flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"><RefreshCw size={13} />Odśwież widok</button></div><div className="mt-4 flex gap-1 overflow-x-auto" role="tablist" aria-label="Sekcje produktu"><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Dane produktu</button><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Benchmark</button><span className="border-b-2 border-primary px-3 py-2 text-xs font-medium text-primary">Aukcje i źródła</span><button onClick={onBack} className="border-b-2 border-transparent px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">Historia</button></div></div><main className="px-6 py-5"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Wybrane", data?.selected_count ?? 0], ["Pobrane", data?.fetched_count ?? 0], ["Błędy pobrania", data?.failed_count ?? 0], ["Przypięte", data?.attached_count ?? 0], ["Niewykorzystane", data?.unattached_count ?? 0]].map(([label, count]) => <div key={String(label)} className="rounded-lg border border-border bg-card p-3"><p className="text-[11px] text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold text-foreground">{count}</p></div>)}</div><div className="mt-3 flex flex-wrap gap-2">{[["Wszystkie", "all"], ["Główne", "primary"], ["Uzupełniające", "supplementary"], ["Oficjalne", "manufacturer"], ["Niewykorzystane", "fetched_but_unattached"], ["Nieudane", "failed"], ["Duplikaty", "duplicate"], ["Odrzucone", "rejected"]].map(([label, key]) => <button key={String(key)} onClick={() => setFilter(key as typeof filter)} className={`rounded-full border px-3 py-1 text-[11px] ${filter === key ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground hover:bg-muted"}`}>{label}</button>)}</div>{loading ? <div className="mt-6 rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">Wczytywanie źródeł produktu…</div> : error ? <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : data?.total === 0 ? <div className="mt-6 rounded-lg border border-dashed border-border bg-card p-10 text-center"><Layers size={28} className="mx-auto text-muted-foreground opacity-50" /><p className="mt-3 text-sm font-medium text-foreground">Ten produkt nie ma jeszcze zapisanych aukcji.</p><p className="mt-1 text-xs text-muted-foreground">Uruchom research, aby przypisać źródła do produktu.</p></div> : <div className="mt-6 space-y-7">{sections.map((section) => section.sources.length > 0 && <section key={section.key}><div className="mb-3 flex items-center gap-2"><h2 className="text-sm font-semibold text-foreground">{section.title}</h2><span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{section.sources.length}</span></div><div className="space-y-3">{section.sources.map((source) => <SourceCard key={source.source_id} source={source} />)}</div></section>)}</div>}</main>{contribution && <SourceContributionPanel data={contribution} onClose={() => { setContribution(null); setSelectedSource(null); }} />}{selectedSource && !contribution && visualSnapshot === null && !visualLoading && <aside className="fixed right-0 top-0 z-50 flex h-full w-[min(560px,100vw)] flex-col border-l border-border bg-card shadow-2xl"><div className="flex items-start justify-between gap-3 border-b border-border p-4"><div className="min-w-0"><p className="text-[11px] text-muted-foreground">{snapshot ? "Lokalny snapshot" : "Użyte dane źródła"}</p><h2 className="mt-1 text-sm font-semibold text-foreground break-words">{selectedSource.title}</h2></div><button onClick={() => { setSelectedSource(null); setSnapshot(null); }} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Zamknij panel"><X size={16} /></button></div>{snapshotLoading ? <p className="p-5 text-sm text-muted-foreground">Otwieranie zapisanego snapshotu…</p> : snapshot ? <div className="min-h-0 flex-1 overflow-auto p-4"><p className="mb-3 text-[11px] text-muted-foreground">{snapshot.snapshot_path}</p><pre className="whitespace-pre-wrap break-words rounded border border-border bg-muted/30 p-3 text-xs leading-relaxed text-foreground">{snapshot.content}</pre></div> : <div className="min-h-0 flex-1 overflow-auto p-4"><div className="grid grid-cols-2 gap-3 text-xs"><div><p className="text-muted-foreground">Źródło</p><p className="mt-1 font-mono text-foreground break-all">{selectedSource.source_id}</p></div><div><p className="text-muted-foreground">Domena</p><p className="mt-1 text-foreground">{selectedSource.domain || "—"}</p></div></div><h3 className="mt-5 text-xs font-semibold text-foreground">Pola oparte o to źródło</h3>{selectedSource.used_fields.length ? <div className="mt-2 space-y-2">{selectedSource.used_fields.map((field, index) => <div key={`${field.field_name}-${index}`} className="rounded border border-border bg-muted/20 p-3"><p className="text-xs font-medium text-foreground">{field.field_name}: <span className="font-normal">{field.value}</span></p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{field.excerpt}</p></div>)}</div> : <p className="mt-2 text-xs text-muted-foreground">To źródło nie ma zapisanego evidence przypisanego do pól produktu.</p>}<div className="mt-5 rounded border border-border bg-muted/20 p-3 text-[11px] text-muted-foreground"><p>Snapshot surowy: <span className="font-mono text-foreground break-all">{selectedSource.raw_snapshot_path || "Brak"}</span></p><p className="mt-1">Snapshot oczyszczony: <span className="font-mono text-foreground break-all">{selectedSource.clean_snapshot_path || "Brak"}</span></p></div></div>}</aside>}{selectedSource && (visualSnapshot !== null || visualLoading) && <VisualSourcePanel source={selectedSource} snapshot={visualSnapshot} blocks={visualBlocks} media={visualMedia} loading={visualLoading} onClose={() => { setSelectedSource(null); setVisualSnapshot(null); setVisualBlocks([]); setVisualMedia([]); }} />}</div>;
}

// ─── Page: Research Wizard ────────────────────────────────────────────────────
const WIZARD_STEPS = ["Produkt", "Źródła", "Potwierdzenie", "Analiza", "Wynik"];

function PageResearch({ previousProductSlug = "" }: { previousProductSlug?: string }) {
  const { products, refreshCatalog } = useCatalog();
  const [step, setStep] = useState(0);
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [categoryKey, setCategoryKey] = useState("");
  const [benchmarkGroup, setBenchmarkGroup] = useState("");
  const [categoryOptions, setCategoryOptions] = useState<CategoryOption[]>([]);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [selectedOfferIds, setSelectedOfferIds] = useState<Set<string>>(new Set());
  const [selectedManufacturerSourceIds, setSelectedManufacturerSourceIds] = useState<Set<string>>(new Set());
  const [previewLoading, setPreviewLoading] = useState(false);
  const [catalogSaving, setCatalogSaving] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [run, setRun] = useState<ApiRun | null>(null);
  const runFailed = run ? isRunFailure(run) : false;
  const runPartial = run ? isRunPartial(run) : false;
  const [requestError, setRequestError] = useState("");
  const activePreviewKeyRef = useRef("");
  const previousPreviewSlugRef = useRef(previousProductSlug);

  const acceptedOffers = preview?.offers.filter((offer) => offer.match_status === "exact_match") || [];
  const probableOffers = preview?.offers.filter((offer) => offer.match_status === "probable_match") || [];
  const previewOffers = preview?.offers || [];
  const rejectedOffers = previewOffers.filter((offer) => offer.match_status === "rejected");
  const manufacturerSources = preview?.manufacturer_sources || [];
  const selectedSourcesCount = selectedOfferIds.size + selectedManufacturerSourceIds.size;
  const includeManufacturerSources = selectedManufacturerSourceIds.size > 0;
  const showSellerColumn = previewOffers.some((offer) => Boolean(offer.seller_name || offer.seller_type || offer.seller_rating !== null || offer.seller_reviews_count !== null));
  const showPriceColumn = previewOffers.some((offer) => Boolean(offer.price));
  const showConditionColumn = previewOffers.some((offer) => Boolean(offer.condition));
  const summary = preview?.summary || {};
  const comparable = (value: string) => value.trim().toLocaleLowerCase("pl-PL");
  const previewKey = (nextBrand: string, nextModel: string, nextCategoryKey: string) => {
    const slugPart = (value: string) => value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l").replace(/Ł/g, "l").toLocaleLowerCase("pl-PL").trim().replace(/\s+/g, "-");
    return `allegro|${slugPart(nextBrand)}|${slugPart(nextModel)}|${nextCategoryKey}`;
  };
  const catalogBrands = [...new Set(products.map((product) => product.brand).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pl"));
  const modelsForBrand = [...new Set(
    products.filter((product) => comparable(product.brand) === comparable(brand)).map((product) => product.name),
  )].sort((a, b) => a.localeCompare(b, "pl"));
  const existingProduct = products.find(
    (product) => comparable(product.brand) === comparable(brand) && comparable(product.name) === comparable(model),
  );
  const selectedCategory = categoryOptions.find((item) => item.category_key === categoryKey);
  const selectedGroups = groupsForCategory(categoryOptions, categoryKey);
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

  useEffect(() => {
    let active = true;
    apiRequest<{ categories: CategoryOption[] }>("/categories")
      .then((result) => { if (active) setCategoryOptions(result.categories || []); })
      .catch(() => { if (active) setRequestError("Nie udało się wczytać obsługiwanych kategorii."); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!existingProduct) return;
    if (!categoryKey && existingProduct.category_key) setCategoryKey(existingProduct.category_key);
    if (!benchmarkGroup && existingProduct.benchmark_group) setBenchmarkGroup(existingProduct.benchmark_group);
  }, [existingProduct?.slug, existingProduct?.category_key, existingProduct?.benchmark_group]);

  const updateBrand = (value: string) => {
    if (value !== brand) clearProductResearchState();
    setBrand(value);
  };

  const updateModel = (value: string) => {
    if (value !== model) clearProductResearchState();
    setModel(value);
  };

  const saveProductToCatalog = async (quiet = false): Promise<boolean> => {
    if (!brand.trim() || !model.trim() || !isValidCategorySelection(categoryOptions, categoryKey, benchmarkGroup)) {
      setRequestError("Wpisz markę i model oraz wybierz kategorię i grupę benchmarkową.");
      return false;
    }
    setCatalogSaving(true);
    setRequestError("");
    try {
      await apiRequest<{ created: boolean; product: CatalogProduct }>("/products", {
        method: "POST",
        body: JSON.stringify({
          brand: brand.trim(), model: model.trim(), category_key: categoryKey, benchmark_group: benchmarkGroup,
        }),
      });
      await refreshCatalog();
      if (!quiet) setRequestError("Produkt zapisano w katalogu. Możesz teraz wyszukać źródła.");
      return true;
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Nie udało się zapisać produktu w katalogu.");
      return false;
    } finally {
      setCatalogSaving(false);
    }
  };

  const checkOffers = async (searchMode: "live" | "cache" = "live") => {
    if (!brand.trim() || !model.trim() || !isValidCategorySelection(categoryOptions, categoryKey, benchmarkGroup)) {
      setRequestError("Wpisz markę i model oraz wybierz kategorię i grupę benchmarkową.");
      return;
    }
    if (!(await saveProductToCatalog(true))) return;
    const submittedBrand = brand.trim();
    const submittedModel = model.trim();
    const expectedKey = previewKey(submittedBrand, submittedModel, categoryKey);
    activePreviewKeyRef.current = expectedKey;
    setPreview(null);
    setSelectedOfferIds(new Set());
    setSelectedManufacturerSourceIds(new Set());
    setPreviewLoading(true);
    setRequestError("");
    try {
      const result = await apiRequest<PreviewResponse>("/research/preview", {
        method: "POST",
        body: JSON.stringify({ brand: submittedBrand, model: submittedModel, marketplace: "allegro", category_key: categoryKey, benchmark_group: benchmarkGroup, search_mode: searchMode, previous_product_slug: previousPreviewSlugRef.current }),
      });
      const responseKey = previewKey(result.requested_brand, result.requested_model, categoryKey);
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
      if (result.status !== "ok") {
        setRequestError(result.message || "Nie udało się pobrać aktualnych ofert.");
        return;
      }
      setSelectedOfferIds(new Set(result.offers.filter((offer) => offer.match_status === "exact_match").map((offer) => offer.offer_id)));
      setSelectedManufacturerSourceIds(new Set(result.manufacturer_sources.filter((source) => source.model_match && source.match_status === "matched").map((source) => source.source_id)));
      await refreshCatalog();
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
      const productSlug = preview?.preview_diagnostics.current_product_slug || existingProduct?.slug;
      if (!productSlug) throw new Error("Nie udało się ustalić produktu zapisanego w katalogu.");
      const created = await apiRequest<ApiRun>("/jobs/research", {
        method: "POST",
        body: JSON.stringify({
          product_slug: productSlug,
          selected_offer_ids: [...selectedOfferIds],
          selected_manufacturer_source_ids: [...selectedManufacturerSourceIds],
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
      const created = await apiRequest<ApiRun>(`/jobs/${run.run_id}/retry`, { method: "POST" });
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
    if (!run || !isRunActive(run)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await apiRequest<ApiRun>(`/jobs/${run.run_id}`);
        setRun(latest);
        if (!isRunActive(latest)) setStep(4);
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
    setCategoryKey("");
    setBenchmarkGroup("");
  };

  const renderOfferTable = (offers: PreviewOffer[], emptyMessage: string, allowSelection: boolean) => {
    if (!offers.length) return <p className="mt-3 text-xs text-muted-foreground">{emptyMessage}</p>;
    return <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="bg-muted/50 text-muted-foreground"><tr><th className="p-3">Wybór</th><th className="p-3">Oferta</th>{showSellerColumn && <th className="p-3">Sprzedawca</th>}{showPriceColumn && <th className="p-3">Cena</th>}{showConditionColumn && <th className="p-3">Stan</th>}<th className="p-3">Typ</th><th className="p-3">Wartość źródła</th><th className="p-3">Dopasowanie</th></tr></thead><tbody className="divide-y divide-border">{offers.map((offer) => {
      const selectable = canSelectPreviewOffer(allowSelection, offer);
      const statusLabel = offer.match_status === "exact_match" ? "Dokładne" : offer.match_status === "probable_match" ? "Prawdopodobne" : "Odrzucone";
      const statusClass = offer.match_status === "exact_match" ? "bg-emerald-50 text-emerald-700" : offer.match_status === "probable_match" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
      const probableReason = offer.rejection_reason === "missing_year_token" ? "Brak roku w tytule" : offer.rejection_reason === "missing_generation_token" ? "Brak oznaczenia generacji w tytule" : "";
      const typeLabel = offer.product_type_label;
      const quality = offer.offer_quality;
      const qualityLabel = quality.level === "high" ? "Wysoka" : quality.level === "medium" ? "Średnia" : "Niska";
      const qualityClass = quality.level === "high" ? "bg-emerald-50 text-emerald-700" : quality.level === "medium" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
      const sellerDetails = [offer.seller_name, offer.seller_type, offer.seller_rating !== null ? `${offer.seller_rating}%` : "", offer.seller_reviews_count !== null ? `${offer.seller_reviews_count} opinii` : ""].filter(Boolean).join(" · ");
      return <tr key={offer.offer_id} className={offer.match_status === "rejected" ? "opacity-60" : ""}><td className="p-3"><input type="checkbox" disabled={!selectable} checked={selectedOfferIds.has(offer.offer_id)} onChange={() => toggleOffer(offer.offer_id)} className="accent-primary disabled:opacity-30" /></td><td className="p-3"><a href={offer.url} target="_blank" rel="noreferrer" className="font-medium text-foreground hover:underline">{offer.title || offer.offer_id}</a><p className="mt-1 flex flex-wrap gap-1 font-mono text-[10px] text-muted-foreground"><span>{offer.offer_id}</span>{offer.sponsored && <span className="rounded bg-muted px-1.5 py-0.5 font-sans">Sponsorowana</span>}</p></td>{showSellerColumn && <td className="p-3 text-muted-foreground">{sellerDetails}</td>}{showPriceColumn && <td className="p-3 text-foreground">{offer.price || ""}</td>}{showConditionColumn && <td className="p-3 text-muted-foreground">{offer.condition || ""}</td>}<td className="p-3 text-muted-foreground">{typeLabel}</td><td className="p-3"><span title={quality.reasons.join("\n")} className={`inline-flex cursor-help rounded px-2 py-1 text-[11px] ${qualityClass}`}>{quality.score}/100 · {qualityLabel}</span></td><td className="p-3"><span className={`rounded px-2 py-1 text-[11px] ${statusClass}`}>{statusLabel}</span>{probableReason && <p className="mt-1 text-[10px] text-amber-700">{probableReason}</p>}</td></tr>;
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
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs text-muted-foreground">Kategoria
                <select value={categoryKey} onChange={(event) => { setCategoryKey(event.target.value); setBenchmarkGroup(""); clearProductResearchState(); }} className="mt-1 w-full rounded border border-border bg-card px-3 py-2 text-sm text-foreground">
                  <option value="">Wybierz kategorię</option>
                  {categoryOptions.map((option) => <option key={option.category_key} value={option.category_key}>{option.label}</option>)}
                </select>
              </label>
              <label className="text-xs text-muted-foreground">Grupa benchmarkowa
                <select value={benchmarkGroup} disabled={!selectedCategory} onChange={(event) => { setBenchmarkGroup(event.target.value); clearProductResearchState(); }} className="mt-1 w-full rounded border border-border bg-card px-3 py-2 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-50">
                  <option value="">{selectedCategory ? "Wybierz grupę" : "Najpierw wybierz kategorię"}</option>
                  {selectedGroups.map((option) => <option key={option.benchmark_group} value={option.benchmark_group}>{option.label}</option>)}
                </select>
              </label>
            </div>
            {existingProduct && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-medium text-amber-800">Ten produkt jest już w katalogu.</p><p className="mt-1 text-[11px] text-amber-700">Możesz bezpiecznie sprawdzić aktualne źródła, ale nie utworzymy drugiego researchu.</p><div className="mt-3 flex gap-2 flex-wrap"><button onClick={() => { window.location.assign(`/products/${existingProduct.slug}`); }} className="px-3 py-1.5 text-xs font-medium border border-amber-300 rounded text-amber-900 hover:bg-amber-100">Otwórz produkt</button><button onClick={() => void checkOffers("live")} disabled={previewLoading} className="px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50">Odśwież dane</button><button onClick={() => void checkOffers("live")} disabled={previewLoading} className="px-3 py-1.5 text-xs font-medium border border-amber-300 rounded text-amber-900 hover:bg-amber-100 disabled:opacity-50">Szukaj aktualnych ofert</button></div></div>}
            {requestError && <div className={`mt-3 rounded border px-3 py-2 text-xs ${requestError.startsWith("Produkt zapisano") ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}><p>{requestError}</p>{preview?.result_mode === "live_failed" && preview.cached_result_available && <div className="mt-2 flex flex-wrap items-center gap-2"><span className="text-[11px]">Dostępne są zapisane wyniki z: {preview.cached_at ? new Date(preview.cached_at).toLocaleString("pl-PL") : "nieznanej daty"}.</span><button onClick={() => void checkOffers("cache")} disabled={previewLoading} className="rounded border border-red-300 bg-white px-2 py-1 text-[11px] font-medium text-red-800 hover:bg-red-100 disabled:opacity-50">Użyj zapisanych wyników</button></div>}</div>}
            {!existingProduct && <div className="mt-6">
              <button
                onClick={() => void saveProductToCatalog()}
                disabled={catalogSaving || !brand.trim() || !model.trim() || !isValidCategorySelection(categoryOptions, categoryKey, benchmarkGroup)}
                className="mr-2 px-4 py-2 text-xs font-medium border border-border rounded hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {catalogSaving ? "Zapisywanie…" : "Dodaj produkt do katalogu"}
              </button>
              <button
                onClick={() => void checkOffers("live")}
                disabled={previewLoading || catalogSaving || !brand.trim() || !model.trim() || !isValidCategorySelection(categoryOptions, categoryKey, benchmarkGroup)}
                className="px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {previewLoading ? "Wyszukiwanie źródeł…" : "Szukaj aktualnych ofert"}
              </button>
            </div>}
          </div>
        )}

        {/* Step 1: Oferty */}
        {step === 1 && (
          <div className="max-w-4xl">
            <h2 className="text-sm font-semibold text-foreground mb-1">Źródła dla {brand.trim()} {model.trim()}</h2>
            <p className="text-xs text-muted-foreground mb-4">Wybór w tym kroku jest tylko podglądem. Nie zapisujemy jeszcze żadnych zmian.</p>
            <div className={`mb-4 rounded-lg border px-3 py-2 text-xs ${preview?.is_fresh ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
              <p className="font-medium">{preview?.result_mode === "live_firecrawl" ? "Aktualne wyszukiwanie Firecrawl" : "Zapisane wyniki"}</p>
              <p className="mt-1">{preview?.result_mode === "live_firecrawl" ? `Pobrano: ${preview.fetched_at ? new Date(preview.fetched_at).toLocaleString("pl-PL") : "—"}` : `Pobrano pierwotnie: ${preview?.cached_at ? new Date(preview.cached_at).toLocaleString("pl-PL") : "—"}`}</p>
            </div>

            <section className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold text-foreground">Oficjalne źródła</h3><span className="text-[11px] text-muted-foreground">{manufacturerSources.length} znaleziono</span></div>
              {manufacturerSources.length ? <div className="mt-3 divide-y divide-border">{manufacturerSources.map((source) => {
                const selectable = source.match_status === "matched" || source.match_status === "uncertain";
                const statusLabel = source.match_status === "matched" ? "Dopasowane" : source.match_status === "uncertain" ? "Niepewne" : source.match_status === "unavailable" ? "Niedostępne" : "Odrzucone";
                const statusClass = source.match_status === "matched" ? "bg-emerald-50 text-emerald-700" : source.match_status === "uncertain" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
                return <div key={source.source_id} className="flex gap-3 py-3"><input type="checkbox" disabled={!selectable} checked={selectedManufacturerSourceIds.has(source.source_id)} onChange={() => toggleManufacturerSource(source.source_id)} className="mt-0.5 accent-primary disabled:opacity-30" /><div className="min-w-0 flex-1"><p className="text-xs font-medium text-foreground">{source.title}</p><p className="mt-1 text-[11px] text-muted-foreground">{source.type_label} · {source.domain || "brak domeny"}</p><div className="mt-1 flex flex-wrap gap-1 text-[10px] text-muted-foreground"><span className="rounded bg-muted px-1.5 py-0.5">{source.cached ? "z cache" : "lokalny zapis niedostępny"}</span><span className="rounded bg-muted px-1.5 py-0.5">pobranie: {source.fetch_status || "nieznany"}</span><span className="rounded bg-muted px-1.5 py-0.5">clean: {source.clean_status || "nieznany"}</span>{source.last_fetched_at && <span className="rounded bg-muted px-1.5 py-0.5">ostatnie: {new Date(source.last_fetched_at).toLocaleDateString("pl-PL")}</span>}{source.refresh_recommended && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">wymaga odświeżenia</span>}</div>{source.url && <a href={source.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"><ExternalLink size={10} />Otwórz źródło</a>}</div><span className={`h-fit rounded px-2 py-1 text-[11px] ${statusClass}`}>{statusLabel}</span></div>;
              })}</div> : <p className="mt-3 text-xs text-muted-foreground">Brak zapisanych oficjalnych źródeł dla tego modelu.</p>}
            </section>

            <section className="mt-4 rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold text-foreground">Oferty Allegro</h3><div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground"><span className="rounded bg-muted px-2 py-1">Znaleziono: {String(summary.unique_offer_ids ?? previewOffers.length)}</span><span className="rounded bg-emerald-50 px-2 py-1 text-emerald-700">Wózki dokładnie dopasowane: {acceptedOffers.length}</span></div></div>
              <div className="mt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Dokładnie dopasowane</h4><span className="text-[11px] text-muted-foreground">{acceptedOffers.length}</span></div><p className="mt-1 text-[11px] text-muted-foreground">Dopasowania są automatycznie zaznaczone.</p>{renderOfferTable(acceptedOffers, "Brak dokładnie dopasowanych ofert.", true)}</div>
              <div className="mt-6 border-t border-border pt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Prawdopodobne dopasowania</h4><span className="text-[11px] text-muted-foreground">{probableOffers.length}</span></div><p className="mt-1 text-[11px] text-muted-foreground">Nie są zaznaczone automatycznie. Możesz wybrać je ręcznie.</p>{renderOfferTable(probableOffers, "Brak prawdopodobnych dopasowań.", true)}</div>
              <div className="mt-6 border-t border-border pt-5"><div className="flex items-center justify-between gap-3"><h4 className="text-xs font-semibold text-foreground">Odrzucone</h4><span className="text-[11px] text-muted-foreground">{rejectedOffers.length}</span></div><p className="mt-1 text-[11px] text-muted-foreground">Oferty innego modelu, akcesoria lub niezgodne typy produktu nie mogą zostać wybrane.</p>{renderOfferTable(rejectedOffers, "Brak odrzuconych ofert.", false)}</div>
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
              <p className="mt-4 text-xs text-muted-foreground">Status: {run?.status === "queued" ? "oczekuje" : run?.status === "leased" ? "przydzielono workerowi" : run?.status === "running" ? "w toku" : run?.status || "—"}</p>
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
    apiRequest<ApiRun>(`/jobs/${runId}`).then((run) => {
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
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const loadRuns = async ({ append = false, background = false } : { append?: boolean; background?: boolean } = {}) => {
    const sequence = ++requestSequence.current;
    if (!append && !background) setLoading(true);
    if (append) setLoadingMore(true);
    setError("");
    try {
      const offset = append ? runs.length : 0;
      const response = await apiRequest<{ total?: number; limit?: number; offset?: number; runs?: ApiRun[] }>(`/jobs?limit=50&offset=${offset}`);
      if (sequence !== requestSequence.current) return;
      const nextRuns = response.runs || [];
      setRuns((current) => append ? [...current, ...nextRuns.filter((next) => !current.some((existing) => existing.run_id === next.run_id))] : nextRuns);
      setTotal(Number.isFinite(response.total) ? Math.max(0, response.total as number) : nextRuns.length);
    } catch (err) {
      if (sequence === requestSequence.current) setError(err instanceof Error ? err.message : "Nie udało się wczytać historii uruchomień.");
    } finally {
      if (!append && !background) setLoading(false);
      if (append) setLoadingMore(false);
    }
  };
  useEffect(() => { void loadRuns(); }, []);
  useEffect(() => {
    if (!runs.some((run) => isRunActive(run))) return;
    const timer = window.setInterval(() => { void loadRuns({ background: true }); }, 2000);
    return () => window.clearInterval(timer);
  }, [runs]);
  const retry = async (runId: string) => {
    setWorking(runId); setError("");
    try { await apiRequest<ApiRun>(`/jobs/${runId}/retry`, { method: "POST" }); await loadRuns({ background: true }); }
    catch (err) { setError(err instanceof Error ? err.message : "Nie udało się ponowić uruchomienia."); }
    finally { setWorking(null); }
  };
  const cancel = async (runId: string) => {
    setWorking(runId); setError("");
    try { await apiRequest<ApiRun>(`/jobs/${runId}/cancel`, { method: "POST" }); await loadRuns({ background: true }); }
    catch (err) { setError(err instanceof Error ? err.message : "Nie udało się anulować uruchomienia."); }
    finally { setWorking(null); }
  };
  const failed = (run: ApiRun) => isRunFailure(run);
  const partial = (run: ApiRun) => isRunPartial(run);
  const succeeded = (run: ApiRun) => isRunSuccess(run);
  const costProgress = (run: ApiRun) => getRunCostProgress(run);
  const sourceCount = (run: ApiRun, key: "sources_selected" | "sources_fetched" | "sources_failed" | "sources_attached") => run[key] ?? run.usage?.[key] ?? null;
  const coverage = (run: ApiRun, key: "coverage_before" | "coverage_after") => run[key] ?? run.usage?.[key] ?? null;
  const statusLabel = (run: ApiRun) => succeeded(run) ? "Sukces" : partial(run) ? "Częściowo" : run.status === "running" ? "W toku" : run.status === "leased" ? "Przydzielono workerowi" : run.status === "queued" ? "W kolejce" : run.status === "timed_out" ? "Przekroczony czas" : run.status === "cancelled" ? "Anulowano" : run.status === "interrupted" ? "Przerwano" : "Błąd";
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
            {runs.filter((run) => succeeded(run)).length} sukces
          </div>
          <span>·</span>
          <div className="flex items-center gap-1">
            <XCircle size={12} className="text-red-400" />
            {runs.filter((run) => failed(run)).length} błędy
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Timeline */}
        <div className="px-6 py-4">
          {error && runs.length > 0 && <div role="status" className="mb-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">Nie udało się odświeżyć historii. Wyświetlam ostatnie zapisane dane. <button className="ml-1 font-medium underline" onClick={() => void loadRuns({ background: true })}>Spróbuj ponownie</button></div>}
          <div className="relative">
            {/* vertical line */}
            <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />

            <div className="flex flex-col gap-0">
              {loading && runs.length === 0 ? <p className="py-4 text-xs text-muted-foreground">Wczytywanie historii uruchomień…</p> : error && runs.length === 0 ? <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700"><p>{error}</p><button className="mt-2 font-medium underline" onClick={() => void loadRuns()}>Spróbuj ponownie</button></div> : runs.length === 0 ? <p className="py-4 text-xs text-muted-foreground">Brak zapisanych uruchomień.</p> : runs.map((run) => (
                <div key={run.run_id} className="flex gap-4 relative pb-4">
                  {/* dot */}
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 z-10 border-2 ${succeeded(run) ? "bg-white border-emerald-400" : failed(run) ? "bg-white border-red-300" : partial(run) ? "bg-white border-amber-300" : "bg-white border-blue-300"}`}>
                    {succeeded(run) ? <CheckCircle2 size={15} className="text-emerald-600" /> : failed(run) ? <XCircle size={15} className="text-red-600" /> : partial(run) ? <AlertCircle size={15} className="text-amber-600" /> : <Clock size={15} className="text-blue-600" />}
                  </div>

                  {/* card */}
                  <div className={`flex-1 bg-card border rounded-lg p-3 ${failed(run) ? "border-red-100" : partial(run) ? "border-amber-100" : "border-border"}`}>
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
                          <span>{sourceCount(run, "sources_selected") ?? "—"} wybranych źródeł</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${succeeded(run) ? "bg-emerald-50 text-emerald-700 border-emerald-200" : failed(run) ? "bg-red-50 text-red-600 border-red-200" : partial(run) ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-blue-50 text-blue-700 border-blue-200"}`}>
                          {statusLabel(run)}
                        </span>
                        {failed(run) && (
                          <button
                            onClick={() => void retry(run.run_id)}
                            disabled={working === run.run_id}
                            className="flex items-center gap-1 px-2 py-0.5 text-[11px] border border-border rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
                          >
                            <RefreshCw size={10} className={working === run.run_id ? "animate-spin" : ""} />
                            {working === run.run_id ? "Ponawiam…" : "Ponów"}
                          </button>
                        )}
                        {canCancelRun(run) && <button onClick={() => void cancel(run.run_id)} disabled={working === run.run_id} className="px-2 py-0.5 text-[11px] border border-border rounded hover:bg-muted">Anuluj</button>}
                      </div>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">Etap: {run.current_step || "—"} · Postęp: {Number.isFinite(run.progress) ? run.progress : 0}% · Coverage: {coverage(run, "coverage_before") ?? "—"}% → {coverage(run, "coverage_after") ?? "—"}%</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">Źródła: {sourceCount(run, "sources_selected") ?? "—"} wybrane · {sourceCount(run, "sources_fetched") ?? "—"} pobrane · {sourceCount(run, "sources_failed") ?? "—"} błędne · {sourceCount(run, "sources_attached") ?? "—"} przypięte</p>
                    {costProgress(run) && <p className="mt-1 text-[11px] text-muted-foreground">Koszt: {costProgress(run)?.used.toFixed(2)} / {costProgress(run)?.limit.toFixed(2)} ({costProgress(run)?.percentage}%)</p>}
                    {run.retry_of && <p className="mt-1 text-[11px] text-muted-foreground">Ponowienie runu: {run.retry_of}</p>}
                    {run.error && (
                      <div className="mt-2 p-2 bg-red-50 border border-red-100 rounded text-[11px] text-red-700 font-mono">
                        {run.error}
                      </div>
                    )}
                    {(failed(run) || partial(run) || isRunActive(run)) && <button onClick={() => setExpandedLog(expandedLog === run.run_id ? null : run.run_id)} className="mt-2 text-[11px] text-primary hover:underline">{expandedLog === run.run_id ? "Ukryj log" : "Pokaż log"}</button>}
                    {expandedLog === run.run_id && <RunLog runId={run.run_id} />}
                  </div>
                </div>
              ))}
            </div>
            {runs.length > 0 && runs.length < total && <button onClick={() => void loadRuns({ append: true })} disabled={loadingMore} className="mt-3 w-full rounded border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50">{loadingMore ? "Wczytywanie…" : `Wczytaj starsze (${runs.length} z ${total})`}</button>}
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

interface ManagedUser {
  id: string;
  email?: string;
  role: "viewer" | "analyst" | "admin";
  must_change_password: boolean;
  created_at?: string;
}

function PageUsers() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [role, setRole] = useState<ManagedUser["role"]>("viewer");
  const [creating, setCreating] = useState(false);
  const load = async () => {
    setLoading(true); setError("");
    try {
      const response = await apiRequest<{ items: ManagedUser[] }>("/admin/users");
      setUsers(Array.isArray(response.items) ? response.items : []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Nie udało się pobrać użytkowników."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const create = async (event: React.FormEvent) => {
    event.preventDefault(); setCreating(true); setError("");
    try {
      await apiRequest("/admin/users", { method: "POST", body: JSON.stringify({ email, role, temporary_password: temporaryPassword }) });
      setEmail(""); setTemporaryPassword(""); setRole("viewer"); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Nie udało się utworzyć użytkownika."); }
    finally { setCreating(false); }
  };
  return <div className="h-full overflow-auto bg-background"><header className="border-b border-border bg-card px-6 py-4"><h1 className="text-base font-semibold text-foreground">Użytkownicy</h1><p className="mt-0.5 text-xs text-muted-foreground">Konta tworzy administrator; nowe konta muszą zmienić hasło przy pierwszym logowaniu.</p></header><main className="mx-auto max-w-4xl space-y-6 px-6 py-6"><section className="rounded-lg border border-border bg-card p-4"><h2 className="text-sm font-semibold text-foreground">Dodaj użytkownika</h2><form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={(event) => void create(event)}><label className="min-w-56 flex-1 text-xs font-medium text-foreground">E-mail<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 block w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label><label className="min-w-56 flex-1 text-xs font-medium text-foreground">Hasło tymczasowe<input required minLength={12} autoComplete="new-password" type="password" value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} className="mt-1 block w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label><label className="text-xs font-medium text-foreground">Rola<select value={role} onChange={(event) => setRole(event.target.value as ManagedUser["role"])} className="mt-1 block rounded border border-border bg-background px-3 py-2 text-sm"><option value="viewer">Viewer — odczyt</option><option value="analyst">Analyst — edycja danych</option><option value="admin">Admin — zarządzanie</option></select></label><button disabled={creating} className="rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">{creating ? "Tworzenie…" : "Utwórz konto"}</button></form></section>{error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}<section className="overflow-hidden rounded-lg border border-border bg-card"><div className="border-b border-border px-4 py-3"><h2 className="text-sm font-semibold text-foreground">Konta</h2></div>{loading ? <p className="p-4 text-sm text-muted-foreground">Wczytywanie użytkowników…</p> : users.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Brak utworzonych kont.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-muted/40 text-xs text-muted-foreground"><tr><th className="px-4 py-2 font-medium">E-mail / identyfikator</th><th className="px-4 py-2 font-medium">Rola</th><th className="px-4 py-2 font-medium">Status</th></tr></thead><tbody>{users.map((user) => <tr key={user.id} className="border-t border-border"><td className="px-4 py-3 text-foreground">{user.email || user.id}</td><td className="px-4 py-3 capitalize text-muted-foreground">{user.role}</td><td className="px-4 py-3 text-muted-foreground">{user.must_change_password ? "Wymaga zmiany hasła" : "Aktywne"}</td></tr>)}</tbody></table></div>}</section></main></div>;
}

// ─── Root App ─────────────────────────────────────────────────────────────────
function FieldnoteApp() {
  const { identity, email, signOut } = useAuth();
  const [page, setPage] = useState<Page>("benchmarki");
  const [products, setProducts] = useState<Product[]>(FALLBACK_PRODUCTS);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [researchSession, setResearchSession] = useState(0);
  const [previousResearchProductSlug, setPreviousResearchProductSlug] = useState("");
  const [comparisonSelection, setComparisonSelection] = useState<string[]>([]);

  const refreshCatalog = async () => {
    try {
      const response = await apiRequest<{ items: CatalogProduct[] }>("/products?limit=500&offset=0");
      if (Array.isArray(response.items)) setProducts(response.items.map(productFromCatalog));
    } catch {
      // Keep the locally generated snapshot as a safe offline fallback.
    }
  };

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

  const openComparison = (ids: string[]) => {
    if (ids.length < 2) return;
    setComparisonSelection(ids);
    setSelectedProductId(ids[0]);
    setPage("produkt-szczegoly");
    window.history.pushState({}, "", `/products/${ids[0]}?tab=benchmark`);
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
    void refreshCatalog();
  }, []);

  useEffect(() => {
    const syncRoute = () => {
      const route = parseFieldnoteRoute(window.location.pathname, new Set(products.map((product) => product.slug)));
      if (route.productSlug) setSelectedProductId(route.productSlug);
      setPage(route.page);
    };
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, [products]);

  const sidebarCollapsed = isNarrow ? !sidebarOpen : false;
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const navigationPage: Page = (page === "produkt-szczegoly" || page === "produkt-zrodla")
    ? (selectedProduct && isLioneloProduct(selectedProduct) ? "benchmarki" : "produkty-konkurencji")
    : page;

  return (
    <CatalogContext.Provider value={{ products, refreshCatalog }}>
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
          current={navigationPage}
          onNav={(p) => { nav(p); if (isNarrow) setSidebarOpen(false); }}
          collapsed={false}
          canManageUsers={canAccessAdminUsers(identity)}
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
              {page === "benchmarki" ? "Benchmarki" :
               page === "produkty-konkurencji" ? "Produkty konkurencji" :
               page === "zrodla" ? "Źródła" :
               page === "produkty" ? "Produkty" :
               page === "produkt-szczegoly" ? `${isLioneloProduct(selectedProduct || { brand: "" }) ? "Benchmarki" : "Produkty konkurencji"} / ${selectedProduct?.name || ""}` :
               page === "produkt-zrodla" ? `Źródła / ${selectedProduct?.name || ""} / Aukcje i źródła` :
               page === "research" ? "Research" :
               page === "users" ? "Użytkownicy" :
               page === "uruchomienia" ? "Uruchomienia" : "Pomoc"}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-3 text-[11px] text-muted-foreground"><span className="hidden sm:block">{email || "Zalogowano"}</span><button onClick={() => void signOut()} className="underline hover:text-foreground">Wyloguj</button></div>
        </div>

        {/* Page content */}
        <div className="flex-1 overflow-hidden">
          {page === "benchmarki" && <PageBenchmarki onDetail={openDetail} />}
          {page === "produkty-konkurencji" && <PageProduktyKonkurencji onDetail={openDetail} />}
          {page === "zrodla" && <PageZrodlaIndex onSources={openSources} />}
          {page === "produkty" && <PageProdukty onDetail={openDetail} onResearch={() => beginResearch()} onCompare={openComparison} />}
          {page === "produkt-szczegoly" && (
            <PageProduktSzczegoly
              productId={selectedProductId}
              onBack={() => nav(isLioneloProduct(selectedProduct || { brand: "" }) ? "benchmarki" : "produkty-konkurencji")}
              backLabel={isLioneloProduct(selectedProduct || { brand: "" }) ? "Benchmarki" : "Produkty konkurencji"}
              onResearch={() => beginResearch(selectedProductId)}
              onSources={() => openSources(selectedProductId)}
              comparisonSelection={comparisonSelection}
            />
          )}
          {page === "produkt-zrodla" && <PageProduktZrodla productId={selectedProductId} onBack={() => openDetail(selectedProductId)} />}
          {page === "research" && <PageResearch key={researchSession} previousProductSlug={previousResearchProductSlug} />}
          {page === "uruchomienia" && <PageUruchomienia />}
          {page === "users" && canAccessAdminUsers(identity) && <PageUsers />}
          {page === "pomoc" && <PagePomoc />}
        </div>
      </div>
    </div>
    </CatalogContext.Provider>
  );
}

export default function App() {
  const { screen, error } = useAuth();
  if (screen === "loading") return <AuthLoadingScreen />;
  if (screen === "configuration-error") return <AuthLoadingScreen error={error || authConfigurationError} />;
  if (screen === "login") return <LoginScreen />;
  if (screen === "change-password") return <ChangeInitialPasswordScreen />;
  return <FieldnoteApp />;
}
