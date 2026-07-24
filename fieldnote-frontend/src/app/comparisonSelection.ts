export type ComparableProduct = {
  id: string;
  benchmark_group?: string;
};

/** Keep the current comparison inside one benchmark group and within 2-5 choices. */
export function toggleComparisonSelection(
  current: ReadonlySet<string>,
  candidate: ComparableProduct,
  products: readonly ComparableProduct[],
): Set<string> {
  const next = new Set(current);
  if (next.has(candidate.id)) {
    next.delete(candidate.id);
    return next;
  }
  if (!candidate.benchmark_group || next.size >= 5) return next;

  const selectedGroup = products.find((product) => next.has(product.id))?.benchmark_group;
  if (selectedGroup && selectedGroup !== candidate.benchmark_group) return next;

  next.add(candidate.id);
  return next;
}

export function canCompareSelection(selected: ReadonlySet<string>): boolean {
  return selected.size >= 2 && selected.size <= 5;
}
