import type { ApplicationItem, ApplicationSort } from '../lib/api';

export interface ApplicationFilters {
  status: string;
  sort: ApplicationSort;
  company: string;
  minScore: number;
  maxScore: number;
  dateFrom: string;
  dateTo: string;
  retryable: boolean;
}

function appliedDate(app: ApplicationItem): string {
  return app.applied_at.slice(0, 10);
}

export function filterApplications(
  apps: ApplicationItem[],
  filters: ApplicationFilters,
  search: string,
): ApplicationItem[] {
  const titleQuery = search.trim().toLowerCase();
  const companyQuery = filters.company.trim().toLowerCase();

  return apps.filter((app) => {
    if (titleQuery && !app.job_title.toLowerCase().includes(titleQuery)) {
      return false;
    }
    if (filters.status && app.status !== filters.status) {
      return false;
    }
    if (companyQuery && !app.company.toLowerCase().includes(companyQuery)) {
      return false;
    }
    if (app.match_score < filters.minScore || app.match_score > filters.maxScore) {
      return false;
    }
    if (filters.retryable && !app.retryable) {
      return false;
    }
    if (filters.dateFrom && appliedDate(app) < filters.dateFrom) {
      return false;
    }
    if (filters.dateTo && appliedDate(app) > filters.dateTo) {
      return false;
    }
    return true;
  });
}

export function sortApplications(
  apps: ApplicationItem[],
  sort: ApplicationSort,
): ApplicationItem[] {
  const sorted = [...apps];
  switch (sort) {
    case 'oldest':
      return sorted.sort((a, b) => a.applied_at.localeCompare(b.applied_at));
    case 'score_desc':
      return sorted.sort((a, b) => b.match_score - a.match_score);
    case 'score_asc':
      return sorted.sort((a, b) => a.match_score - b.match_score);
    case 'company_asc':
      return sorted.sort((a, b) => a.company.localeCompare(b.company));
    case 'company_desc':
      return sorted.sort((a, b) => b.company.localeCompare(a.company));
    case 'title_asc':
      return sorted.sort((a, b) => a.job_title.localeCompare(b.job_title));
    case 'title_desc':
      return sorted.sort((a, b) => b.job_title.localeCompare(a.job_title));
    case 'newest':
    default:
      return sorted.sort((a, b) => b.applied_at.localeCompare(a.applied_at));
  }
}

export function paginateApplications(
  apps: ApplicationItem[],
  page: number,
  perPage: number,
): ApplicationItem[] {
  const offset = (page - 1) * perPage;
  return apps.slice(offset, offset + perPage);
}

export function countActiveFilters(filters: ApplicationFilters, search: string): number {
  let count = 0;
  if (filters.status) count += 1;
  if (search.trim()) count += 1;
  if (filters.company.trim()) count += 1;
  if (filters.minScore > 0 || filters.maxScore < 100) count += 1;
  if (filters.dateFrom || filters.dateTo) count += 1;
  if (filters.retryable) count += 1;
  if (filters.sort !== 'newest') count += 1;
  return count;
}
