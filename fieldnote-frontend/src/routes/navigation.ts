export type FieldnotePage = "produkty" | "produkt-szczegoly" | "produkt-zrodla" | "research" | "uruchomienia" | "pomoc";

export function routeForPage(page: FieldnotePage): string {
  return {
    produkty: "/products",
    research: "/research",
    uruchomienia: "/runs",
    pomoc: "/help",
  }[page] || "/products";
}

export function parseFieldnoteRoute(pathname: string, knownProductSlugs: Set<string>): { page: FieldnotePage; productSlug?: string } {
  const sources = pathname.match(/^\/products\/([^/]+)\/([^/]+)\/sources$/);
  if (sources) {
    const productSlug = `${sources[1]}__${sources[2]}`;
    if (knownProductSlugs.has(productSlug)) return { page: "produkt-zrodla", productSlug };
  }
  const product = pathname.match(/^\/products\/([^/]+)$/);
  if (product && knownProductSlugs.has(product[1])) return { page: "produkt-szczegoly", productSlug: product[1] };
  if (pathname === "/research") return { page: "research" };
  if (pathname === "/runs") return { page: "uruchomienia" };
  if (pathname === "/help") return { page: "pomoc" };
  return { page: "produkty" };
}
