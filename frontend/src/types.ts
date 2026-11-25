export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type FindingStatus = 'confirmed' | 'needs_review' | 'rejected'
export type CheckStatus = 'pass' | 'fail' | 'needs_review' | 'not_applicable' | 'not_evaluated'
export interface Check { criterion: string; status: CheckStatus; explanation: string }
export interface Evidence { requirement_id: string | null; quote: string; section: string; start: number; end: number; page: number | null }
export interface Fix {
  original_text: string; proposed_text: string; rationale: string; changes: string
  acceptance_criteria: string; clarification_required: boolean; clarification_question: string
}
export interface Finding {
  id: string; title: string; category: string; criteria: string[]; severity: Severity; confidence: number
  requirement_ids: string[]; evidence: Evidence[]; explanation: string; impact: string; recommendation: string
  status: FindingStatus; source: string; validation_note: string; fix: Fix | null
}
export interface Requirement {
  id: string; source_id: string | null; summary: string; text: string; section: string
  source_start: number; source_end: number; requirement_type: string; type_confidence: number; checks: Check[]
}
export interface Stage { id: string; title: string; status: 'completed' | 'partial' | 'failed' | 'skipped'; message: string; seconds: number; models: string[] }
export interface Report {
  document_name: string; document_text: string; analyzed_at: string; duration_seconds: number
  agent_version: string; model_name: string; status: 'completed' | 'partial' | 'failed'
  stages: Stage[]; requirements: Requirement[]; set_checks: Check[]; findings: Finding[]; rejected_findings: Finding[]
  readiness: { score: number | null; status: string; coverage: number; dimensions: { id: string; title: string; weight: number; score: number | null }[] }
  summary: Record<string, number>
  verdict: { development: string; testing: string; text: string; priorities: string[] }
}
export interface AnalysisInfo {
  analysis_id: string; document_name: string; status: 'queued' | 'running' | 'completed' | 'partial' | 'failed'
  stage: string; progress: number; message: string; created_at: string; done: string[]; active: string[]
  score?: number | null; readiness_status?: string; findings_count?: number; requirements_count?: number
}
export interface Health { model: string; model_ready: boolean; version: string; stages: { id: string; title: string }[] }
