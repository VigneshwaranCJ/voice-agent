export interface User {
  id: string
  email: string
  full_name: string
  role: 'platform_admin' | 'tenant_admin' | 'tenant_agent'
  tenant_id: string | null
  tenant_name: string | null
}

export interface Tenant { id: string; name: string; slug: string; industry: string; is_active: boolean; created_at: string }

export interface AgentConfig {
  id?: string
  version?: number
  created_at?: string
  persona_name: string
  personality: string
  system_instructions: string
  greeting: Record<string, string>
  enabled_tools: string[]
  workflows: Record<string, unknown>
  escalation_policy: Record<string, unknown>
  llm_settings: Record<string, unknown>
}

export interface Agent {
  id: string
  tenant_id: string
  name: string
  industry: string
  default_language: string
  languages: string[]
  public_widget_enabled: boolean
  is_active: boolean
  created_at: string
  config?: AgentConfig | null
}

export interface ToolInfo { name: string; description: string; industry: string; requires_confirmation: boolean; is_write: boolean }

export interface KnowledgeDoc {
  id: string; agent_id: string | null; title: string; source_type: string; filename: string | null
  status: string; error: string | null; chunk_count: number; created_at: string
}

export interface Conversation {
  id: string; agent_id: string; channel: string; status: string; language: string | null
  languages_used: string[]; intents: string[]; summary: string | null; resolved: boolean | null
  created_at: string; ended_at: string | null
}

export interface Message { id: string; role: string; content: string; language: string | null; interrupted: boolean; meta: Record<string, unknown>; created_at: string }

export const LANGUAGES: Record<string, string> = {
  'en-IN': 'English', 'ta-IN': 'Tamil', 'hi-IN': 'Hindi', 'te-IN': 'Telugu', 'kn-IN': 'Kannada',
  'ml-IN': 'Malayalam', 'bn-IN': 'Bengali', 'mr-IN': 'Marathi', 'gu-IN': 'Gujarati', 'pa-IN': 'Punjabi', 'od-IN': 'Odia',
}
