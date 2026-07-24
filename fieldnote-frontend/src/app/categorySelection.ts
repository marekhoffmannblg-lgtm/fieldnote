export interface CategoryOption {
  category_key: string;
  label: string;
  benchmark_groups: Array<{ benchmark_group: string; label: string }>;
}

export function groupsForCategory(categories: CategoryOption[], categoryKey: string) {
  return categories.find((category) => category.category_key === categoryKey)?.benchmark_groups || [];
}

export function isValidCategorySelection(categories: CategoryOption[], categoryKey: string, benchmarkGroup: string) {
  return groupsForCategory(categories, categoryKey).some((group) => group.benchmark_group === benchmarkGroup);
}
