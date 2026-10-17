/**
 * TanStack Query hooks. Query keys and cache invalidation live here so every screen that shows
 * the same record refreshes together (e.g. a profile save makes match reports stale).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, type TrackerFilters } from "./endpoints";
import type * as T from "./types";

/** The session check used by ConnectionGate; reset it to make the gate re-check the token. */
export const SESSION_KEY = ["session"] as const;

export const keys = {
  settings: ["settings"] as const,
  dashboard: ["dashboard"] as const,
  profile: ["profile"] as const,
  profileVersions: ["profile", "versions"] as const,
  roles: ["roles"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["jobs", id] as const,
  captures: ["captures"] as const,
  analysis: (id: string) => ["analysis", id] as const,
  match: (id: string) => ["match", id] as const,
  tailoring: (id: string) => ["tailoring", id] as const,
  resumes: ["resumes"] as const,
  jobResumes: (id: string) => ["resumes", "job", id] as const,
  resume: (id: string) => ["resume", id] as const,
  tracker: (f: TrackerFilters) => ["tracker", f] as const,
  duplicates: ["tracker", "duplicates"] as const,
};

/** Invalidate everything derived from the given roots. */
function refresh(qc: QueryClient, ...roots: string[]) {
  return Promise.all(roots.map((root) => qc.invalidateQueries({ queryKey: [root] })));
}

/** Anything that depends on the profile: matches, tailoring and validation results, dashboard. */
export const PROFILE_DEPENDENTS = ["profile", "roles", "match", "tailoring", "resume", "dashboard"];
/** Anything that depends on jobs and their records. */
export const JOB_DEPENDENTS = ["jobs", "analysis", "match", "tailoring", "resumes", "resume", "tracker", "dashboard", "captures"];

// ---- queries ------------------------------------------------------------------------

export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: ({ signal }) => api.settings.get(signal) });
export const useDashboard = () => useQuery({ queryKey: keys.dashboard, queryFn: ({ signal }) => api.dashboard(signal) });
export const useProfile = () => useQuery({ queryKey: keys.profile, queryFn: ({ signal }) => api.profile.get(signal) });
export const useProfileVersions = () =>
  useQuery({ queryKey: keys.profileVersions, queryFn: ({ signal }) => api.profile.versions(signal) });
export const useRoles = () => useQuery({ queryKey: keys.roles, queryFn: ({ signal }) => api.roles.list(signal) });
export const useJobs = () => useQuery({ queryKey: keys.jobs, queryFn: ({ signal }) => api.jobs.list(signal) });
export const useJob = (id: string) => useQuery({ queryKey: keys.job(id), queryFn: ({ signal }) => api.jobs.get(id, signal) });
export const useCaptures = () => useQuery({ queryKey: keys.captures, queryFn: ({ signal }) => api.jobs.captures(signal) });
export const useAnalysis = (id: string) =>
  useQuery({ queryKey: keys.analysis(id), queryFn: ({ signal }) => api.analysis.get(id, signal) });
export const useMatch = (id: string) => useQuery({ queryKey: keys.match(id), queryFn: ({ signal }) => api.match.get(id, signal) });
export const useTailoring = (id: string) =>
  useQuery({ queryKey: keys.tailoring(id), queryFn: ({ signal }) => api.resumes.tailoring(id, signal) });
export const useAllResumes = () => useQuery({ queryKey: keys.resumes, queryFn: ({ signal }) => api.resumes.listAll(signal) });
export const useJobResumes = (id: string) =>
  useQuery({ queryKey: keys.jobResumes(id), queryFn: ({ signal }) => api.resumes.forJob(id, signal) });
export const useResume = (id: string | undefined) =>
  useQuery({
    queryKey: keys.resume(id ?? ""),
    queryFn: ({ signal }) => api.resumes.get(id as string, signal),
    enabled: Boolean(id),
  });
export const useTracker = (filters: TrackerFilters) =>
  useQuery({
    queryKey: keys.tracker(filters),
    queryFn: ({ signal }) => api.tracker.get(filters, signal),
    placeholderData: keepPreviousData,
  });
export const useDuplicates = () => useQuery({ queryKey: keys.duplicates, queryFn: ({ signal }) => api.tracker.duplicates(signal) });

// ---- mutations ----------------------------------------------------------------------

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ profile, expectedVersion }: { profile: T.MasterProfile | Record<string, unknown>; expectedVersion: number | null }) =>
      api.profile.save(profile, expectedVersion),
    onSuccess: (out) => {
      qc.setQueryData<T.ProfileView>(keys.profile, (old) => (old ? { ...old, profile: out.profile } : old));
      return refresh(qc, ...PROFILE_DEPENDENTS);
    },
  });
}

export function useProfileAction<A>(fn: (arg: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => refresh(qc, ...PROFILE_DEPENDENTS) });
}

export function useRoleAction<A>(fn: (arg: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => refresh(qc, "roles", "tailoring", "match", "dashboard") });
}

export function useJobAction<A, R = unknown>(fn: (arg: A) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => refresh(qc, ...JOB_DEPENDENTS) });
}

/** Deleting a job: drop its cached records instead of refetching them (they'd 404), then refresh lists. */
export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.jobs.remove,
    onSuccess: (_, id) => {
      for (const key of [keys.job(id), keys.analysis(id), keys.match(id), keys.tailoring(id), keys.jobResumes(id)]) {
        qc.removeQueries({ queryKey: key, exact: true });
      }
      void refresh(qc, "jobs", "resumes", "tracker", "dashboard");
    },
  });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.settings.patch,
    onSuccess: (view) => {
      qc.setQueryData(keys.settings, view);
      return refresh(qc, "tailoring");
    },
  });
}
