/**
 * One voice call to a hosted Sarvam Voice Agent, from the browser.
 *
 * The Sarvam SDK asks `{baseUrl}orgs/{org}/workspaces/{ws}/apps/{app}/url` for a signed WebSocket URL. `baseUrl` is
 * always our own server, which adds the Sarvam key there (it never reaches the browser); the audio then flows
 * between the browser and Sarvam directly, so our host doesn't need WebSocket support.
 */
import { AgentState, BrowserAudioInterface, ConversationAgent, InteractionType } from 'sarvam-conv-ai-sdk/browser'

export interface SarvamIds { org_id: string; workspace_id: string; app_id: string }

/** What the server returns for a call: ids plus optional business context for the agent's prompt. */
export interface SarvamCallConfig extends SarvamIds { agent_variables?: Record<string, string> }

export type CallStatus = 'connecting' | 'listening' | 'speaking' | 'ended' | 'error'

export interface CallOptions {
  ids: SarvamCallConfig
  /** Our session route, ending in "/" (e.g. "/api/v1/sarvam/runtime/AGENT_ID/"). */
  baseUrl: string
  /** Extra headers for that route, e.g. the dashboard login. Leave empty for cross-site use (no preflight). */
  headers?: Record<string, string>
  userId?: string
  onStatus?: (s: CallStatus) => void
  onTranscript?: (role: string, text: string) => void
  onError?: (message: string) => void
  /** Once, when a call that connected has ended: Sarvam's interaction id, so the server can save the transcript. */
  onFinished?: (interactionId: string) => void
  /** The caller talked over the agent: the SDK has already cut the agent's audio (barge-in). */
  onInterrupt?: () => void
}

export interface CallHandle { stop: () => Promise<void> }

const RATE = 16000

function statusFor(s: AgentState): CallStatus | null {
  switch (s) {
    case AgentState.CONNECTING: case AgentState.CONNECTED: return 'connecting'
    case AgentState.LISTENING: return 'listening'
    case AgentState.SPEAKING: return 'speaking'
    case AgentState.ERROR: return 'error'
    case AgentState.IDLE: return 'ended'
    default: return null
  }
}

function explain(e: unknown): string {
  const name = (e as { name?: string })?.name ?? ''
  const msg = (e as Error)?.message ?? String(e)
  if (name === 'NotAllowedError') return 'Microphone permission was denied.'
  if (/402|credit/i.test(msg)) return 'The voice service is out of credits.'
  if (/AuthenticationError|ForbiddenError|401|403/.test(name + msg)) return 'The voice service rejected the request.'
  if (/NotFoundError|404/.test(name + msg)) return 'This agent is not set up for voice calls.'
  if (/RateLimit|429/.test(name + msg)) return 'Too many calls right now. Please try again shortly.'
  return 'The call could not start. Please try again.'
}

export async function startSarvamCall(o: CallOptions): Promise<CallHandle> {
  let ended = false          // session torn down (by us, the agent or the network)
  let failed = false         // ended with an error: keep the 'error' status instead of reporting 'ended'
  let userHungUp = false
  let interactionId: string | undefined
  let reported = false
  const fail = (message: string) => { if (!failed) { failed = true; o.onError?.(message); o.onStatus?.('error') } }
  const finished = () => {
    if (reported || !interactionId) return
    reported = true
    o.onFinished?.(interactionId)
  }
  const audio = new BrowserAudioInterface(RATE)
  const { agent_variables: agentVariables, ...ids } = o.ids
  const agent = new ConversationAgent({
    apiKey: '', // the key is added server-side by our session route
    baseUrl: o.baseUrl,
    customHeaders: o.headers,
    audioInterface: audio,
    config: {
      ...ids,
      ...(agentVariables ? { agent_variables: agentVariables } : {}),
      user_identifier: o.userId ?? `web-${Math.random().toString(36).slice(2, 10)}`,
      user_identifier_type: 'custom',
      interaction_type: InteractionType.CALL,
      input_sample_rate: RATE,
      output_sample_rate: RATE,
    },
    stateCallback: (s) => {
      interactionId = agent.getInteractionId() ?? interactionId // remember it while connected
      const st = statusFor(s)
      if (st === 'error') fail('The call ran into a problem and ended.')
      else if (st && st !== 'ended' && !ended) o.onStatus?.(st)
    },
    transcriptCallback: async (m) => {
      interactionId = agent.getInteractionId() ?? interactionId
      if (m.content) o.onTranscript?.(String(m.role), m.content)
    },
    telemetryCallback: (e) => {
      if (e.name === 'interaction_connected') interactionId = e.interactionId ?? interactionId
      if (e.name === 'user_interrupted') o.onInterrupt?.()
      if (e.name === 'session_ended' && !userHungUp) {
        const by = (e.properties as { initiatedBy?: string }).initiatedBy
        if (by === 'network' || by === 'error') fail('The call dropped. Check your connection and call again.')
      }
    },
    endCallback: async () => { void teardown() }, // the agent ended the call
  })
  async function teardown() {
    if (ended) { finished(); return }
    ended = true
    interactionId = agent.getInteractionId() ?? interactionId
    await agent.stop().catch(() => {})
    await audio.stop().catch(() => {}) // releases the microphone even if the call never connected
    if (!failed) o.onStatus?.('ended')
    finished()
  }
  const stop = async () => { userHungUp = true; await teardown() }

  // The SDK opens the microphone in the background and doesn't surface a denial; ask first so we can explain it.
  try {
    const probe = await navigator.mediaDevices.getUserMedia({ audio: true })
    probe.getTracks().forEach((t) => t.stop())
  } catch (e) {
    fail(explain(e))
    throw e
  }
  o.onStatus?.('connecting')
  try {
    await agent.start()
    if (!(await agent.waitForConnect(15))) throw new Error('timeout')
    interactionId = agent.getInteractionId() ?? interactionId
  } catch (e) {
    fail(explain(e))
    interactionId = undefined // never connected: nothing to save
    await teardown()
    throw e
  }
  // The socket closing (agent hung up, network dropped) always ends the call and releases the microphone.
  agent.waitForDisconnect().then(() => teardown()).catch(() => {})
  return { stop }
}
