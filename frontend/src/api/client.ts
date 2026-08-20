import type {
  Assessment,
  AssessmentDetail,
  Dashboard,
  FindingDetail,
  FindingListItem,
  FindingStatus,
  ImportSummary,
  Owner,
  Priority,
  Remediation,
  ValidationRecord,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers:
      options?.body && !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : undefined,
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ? JSON.stringify(body.detail) : detail
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export interface FindingFilters {
  search?: string
  priority?: Priority
  status?: FindingStatus
  category?: string
  severity?: string
  owner_id?: number
}

export const api = {
  // Dashboard
  getDashboard: () => request<Dashboard>('/dashboard'),

  // Assessments
  listAssessments: () => request<Assessment[]>('/assessments'),
  getAssessment: (id: number) => request<AssessmentDetail>(`/assessments/${id}`),

  // Pentera import
  importPentera: (form: FormData) =>
    request<ImportSummary>('/imports/pentera', { method: 'POST', body: form }),

  // Findings
  listFindings: (filters: FindingFilters = {}) => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== '') params.set(k, String(v))
    })
    const qs = params.toString()
    return request<FindingListItem[]>(`/findings${qs ? `?${qs}` : ''}`)
  },
  getFinding: (id: number) => request<FindingDetail>(`/findings/${id}`),
  updateFinding: (id: number, payload: { owner_id?: number | null; status?: FindingStatus }) =>
    request<FindingDetail>(`/findings/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  // Owners
  listOwners: () => request<Owner[]>('/owners'),
  createOwner: (payload: { name: string; team?: string; email?: string }) =>
    request<Owner>('/owners', { method: 'POST', body: JSON.stringify(payload) }),

  // Remediations
  createRemediation: (payload: {
    finding_id: number
    owner_id?: number | null
    status?: FindingStatus
    recommended_action?: string
    remediation_notes?: string
    due_date?: string
  }) => request<Remediation>('/remediations', { method: 'POST', body: JSON.stringify(payload) }),

  // Validations
  createValidation: (payload: {
    finding_id: number
    validation_method?: string
    evidence?: string
    validation_date: string
    result: 'PASS' | 'FAIL' | 'INCONCLUSIVE'
    validated_by?: string
    notes?: string
  }) => request<ValidationRecord>('/validations', { method: 'POST', body: JSON.stringify(payload) }),
}

export { ApiError }
