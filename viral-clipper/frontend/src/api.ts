// API client for the ViralClipper backend

const BASE = '/api'

export type SubtitleStyle = 'default' | 'neon' | 'minimal' | 'bold'
export type Category = 'humor' | 'shock' | 'insight' | 'drama' | 'motivation' | 'controversy'
export type BestMoment = 'hook' | 'middle' | 'end'
export type JobStatus = 'queued' | 'running' | 'done' | 'error'

export interface ProcessRequest {
  url: string
  subtitle_style?: SubtitleStyle
  max_clips?: number
  min_duration?: number
  max_duration?: number
  no_subtitles?: boolean
}

export interface Job {
  id: string
  status: JobStatus
  step: string
  progress: number
  url: string
  error: string | null
  result: { video_id: string; clips: Clip[] } | null
}

export interface Video {
  id: string
  url: string
  title: string
  channel: string
  duration: number
  language: string
  processed_at: string
  metadata: Record<string, unknown>
  clips?: Clip[]
}

export interface Clip {
  id: string
  video_id: string
  title: string
  start_time: number
  end_time: number
  duration: number
  viral_score: number
  category: Category
  hook: string
  reasoning: string
  suggested_caption: string
  file_path: string
  thumbnail_path: string
  subtitle_style: SubtitleStyle
  created_at: string
}

export interface Feedback {
  performance_rating: number
  views?: number
  likes?: number
  comments?: number
  retention_rate?: number
  best_moment?: BestMoment
  notes?: string
}

export interface Stats {
  total_videos: number
  total_clips: number
  total_feedback: number
  avg_viral_score: number
  pending_feedback: number
  top_clips: Array<{
    id: string
    title: string
    viral_score: number
    views: number
    performance_rating: number
  }>
}

export interface LearningProfile {
  total_clips_rated: number
  avg_accuracy: number
  best_performing_categories: string[]
  optimal_duration_range: [number, number] | null
  best_hook_types: string[]
  worst_patterns: string[]
  channel_insights: Record<string, { avg_score: number; count: number }>
  category_stats?: Record<string, { count: number; avg_rating: number; avg_views: number }>
  learned_rules: string[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Unknown error')
  }
  return res.json() as Promise<T>
}

// ─── Process ───────────────────────────────────────────────────────────────

export const processVideo = (req: ProcessRequest) =>
  request<{ job_id: string; status: string }>('/process', {
    method: 'POST',
    body: JSON.stringify(req),
  })

// ─── Jobs ──────────────────────────────────────────────────────────────────

export const getJobs = () => request<Job[]>('/jobs')
export const getJob = (id: string) => request<Job>(`/jobs/${id}`)

// ─── Videos ────────────────────────────────────────────────────────────────

export const getVideos = (limit = 50, offset = 0) =>
  request<Video[]>(`/videos?limit=${limit}&offset=${offset}`)

export const getVideo = (id: string) => request<Video>(`/videos/${id}`)

// ─── Clips ─────────────────────────────────────────────────────────────────

export const getClips = (limit = 100) => request<Clip[]>(`/clips?limit=${limit}`)
export const getClip = (id: string) => request<Clip>(`/clips/${id}`)
export const getPendingFeedback = () => request<Clip[]>('/clips/pending-feedback')

export const submitFeedback = (clipId: string, feedback: Feedback) =>
  request<{ status: string; learning_profile: LearningProfile }>(
    `/clips/${clipId}/feedback`,
    { method: 'POST', body: JSON.stringify(feedback) }
  )

export const clipVideoUrl = (id: string) => `${BASE}/clips/${id}/video`
export const clipThumbnailUrl = (id: string) => `${BASE}/clips/${id}/thumbnail`

// ─── Learning ──────────────────────────────────────────────────────────────

export const getLearningProfile = () => request<LearningProfile>('/learning/profile')

// ─── Stats ─────────────────────────────────────────────────────────────────

export const getStats = () => request<Stats>('/stats')

// ─── Reanalyze ─────────────────────────────────────────────────────────────

export const reanalyzeVideo = (videoId: string) =>
  request<{ job_id: string; status: string }>(`/reanalyze/${videoId}`, { method: 'POST' })
