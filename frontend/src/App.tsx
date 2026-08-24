import { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000/api';

// --- Interfaces ---
interface Position3D {
  x: number;
  y: number;
  z: number;
  frame_id?: string;
}

interface OrientationRPY {
  roll: number;
  pitch: number;
  yaw: number;
}

interface RobotState {
  position: Position3D;
  orientation: OrientationRPY;
  battery: number;
  is_moving: boolean;
  velocity_linear: number;
}

interface NavigationStatus {
  state: string;
  status_text: string;
  progress: number;
}

interface RobotContext {
  robot_pose: RobotState;
  navigation_status: NavigationStatus;
}

interface ReasoningBreakdown {
  user_intent: string;
  scene_analysis: string;
  decision_process: string;
  safety_considerations: string;
  confidence: number;
}

interface ActionStep {
  step: number;
  action: string;
  parameters?: Record<string, unknown>;
  expected_result?: string;
}

interface PlannerResponse {
  goal?: string;
  task_status?: string;
  plan?: ActionStep[];
  target?: Record<string, unknown>;
  explanation_for_user?: string;
  clarification_required?: boolean;
  clarification_question?: string;
  reasoning: ReasoningBreakdown;
}

interface TaskStatus {
  active_task: string;
  task_history: Array<{ task: string; status: string; started_at?: string; ended_at?: string }>;
  exploration_status?: string;
}

interface NavHistoryEntry {
  target: string;
  goal?: string;
  result: string;
  timestamp: string;
}

interface NavHistory {
  navigation_history: NavHistoryEntry[];
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  timestamp: string;
  commandText?: string;
  goal?: string;
  explanation?: string;
  reasoning?: ReasoningBreakdown;
  plan?: ActionStep[];
  status?: 'success' | 'error' | 'safety_rejected';
  errorMessage?: string;
}

// --- Sub-components ---

const CameraFeedPanel = () => {
  const [timestamp, setTimestamp] = useState(Date.now());
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => setTimestamp(Date.now()), 500); // 2FPS
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="glass-panel p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
          <h2 className="text-sm font-semibold tracking-wide uppercase text-fuchsia-400">Live Camera Feed</h2>
        </div>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
          2 FPS • RGB
        </span>
      </div>

      <div className="rounded-xl overflow-hidden border border-slate-700/50 bg-black aspect-video flex items-center justify-center relative shadow-inner">
        <img
          src={`${API_BASE}/camera/frame.jpg?t=${timestamp}`}
          alt="Live Camera Feed"
          className={`w-full h-full object-cover transition-opacity duration-300 ${hasError ? 'opacity-0' : 'opacity-100'}`}
          onError={() => setHasError(true)}
          onLoad={() => setHasError(false)}
        />
        {hasError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-950/90 text-slate-500 font-mono text-xs">
            <svg className="w-7 h-7 text-slate-600 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3" />
            </svg>
            <span>NO SIGNAL / FEED OFFLINE</span>
          </div>
        )}
      </div>
    </div>
  );
};

const RobotStatePanel = ({ context, taskState }: { context: RobotContext | null; taskState: TaskStatus | null }) => {
  if (!context) {
    return (
      <div className="glass-panel p-4 flex items-center justify-center text-sm text-slate-400">
        <div className="w-4 h-4 border-2 border-sky-400 border-t-transparent rounded-full animate-spin mr-2" />
        Connecting telemetry...
      </div>
    );
  }

  const { robot_pose, navigation_status } = context;
  const batteryPct = Math.round(robot_pose.battery);

  return (
    <div className="glass-panel p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide uppercase text-sky-400">System Telemetry</h2>
        <span className="text-[11px] font-mono text-slate-400">
          X: {robot_pose.position.x.toFixed(1)} | Y: {robot_pose.position.y.toFixed(1)} | Yaw: {robot_pose.orientation.yaw.toFixed(2)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        {/* Battery */}
        <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Battery</span>
            <span className="font-mono text-emerald-400 font-bold">{batteryPct}%</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden mt-2">
            <div
              className={`h-full transition-all duration-500 rounded-full ${
                batteryPct > 50 ? 'bg-emerald-400' : batteryPct > 20 ? 'bg-amber-400' : 'bg-rose-500'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, batteryPct))}%` }}
            />
          </div>
        </div>

        {/* Navigation State */}
        <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
          <div className="text-xs text-slate-400">Nav State</div>
          <div className="text-sm font-semibold text-sky-300 capitalize truncate mt-0.5">
            {navigation_status.state || 'Idle'}
          </div>
        </div>

        {/* Speed */}
        <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
          <div className="text-xs text-slate-400">Speed (m/s)</div>
          <div className="text-sm font-mono font-medium text-slate-200 mt-0.5">
            {robot_pose.velocity_linear.toFixed(2)}
          </div>
        </div>

        {/* Exploration Status */}
        <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
          <div className="text-xs text-slate-400">Exploration</div>
          <div
            className={`text-sm font-semibold capitalize truncate mt-0.5 ${
              taskState?.exploration_status === 'active'
                ? 'text-amber-400 animate-pulse'
                : taskState?.exploration_status === 'completed'
                ? 'text-emerald-400'
                : 'text-slate-400'
            }`}
          >
            {taskState?.exploration_status || 'Standby'}
          </div>
        </div>
      </div>
    </div>
  );
};

const NavigationAndControlsPanel = ({
  navHistory,
  handleManual,
  handleStop,
}: {
  navHistory: NavHistory | null;
  handleManual: (linear: number, angular: number) => void;
  handleStop: () => void;
}) => {
  const [activeTab, setActiveTab] = useState<'history' | 'manual'>('history');

  return (
    <div className="glass-panel p-4 flex flex-col gap-3 flex-1 min-h-0">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('history')}
            className={`text-xs font-semibold px-3 py-1 rounded-lg transition-all cursor-pointer ${
              activeTab === 'history'
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Nav History
          </button>
          <button
            onClick={() => setActiveTab('manual')}
            className={`text-xs font-semibold px-3 py-1 rounded-lg transition-all cursor-pointer ${
              activeTab === 'manual'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Manual Teleop
          </button>
        </div>

        <button
          onClick={handleStop}
          className="text-xs px-2.5 py-1 bg-rose-600/30 hover:bg-rose-600 text-rose-300 hover:text-white rounded-lg border border-rose-500/40 font-bold transition-all cursor-pointer shadow-[0_0_10px_rgba(225,29,72,0.2)]"
        >
          STOP
        </button>
      </div>

      {activeTab === 'history' ? (
        <div className="flex flex-col gap-2 overflow-y-auto flex-1 max-h-52 pr-1">
          {!navHistory?.navigation_history || navHistory.navigation_history.length === 0 ? (
            <div className="text-slate-500 italic text-xs text-center py-6">No navigation history recorded yet.</div>
          ) : (
            [...navHistory.navigation_history].reverse().map((entry, idx) => (
              <div
                key={idx}
                className="bg-slate-900/50 p-2 rounded-lg border border-slate-800/80 flex justify-between items-center text-xs"
              >
                <div className="min-w-0 pr-2">
                  <div className="font-medium text-slate-200 truncate">{entry.target || entry.goal || 'Goal'}</div>
                  <div className="text-[10px] text-slate-400 font-mono">
                    {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : 'Recent'}
                  </div>
                </div>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full shrink-0 ${
                    entry.result?.toLowerCase().includes('success')
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  }`}
                >
                  {entry.result || 'Done'}
                </span>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center gap-3 py-2 flex-1">
          <div className="grid grid-cols-3 gap-2 w-40">
            <div />
            <button
              onMouseDown={() => handleManual(0.5, 0.0)}
              onMouseUp={() => handleManual(0.0, 0.0)}
              onMouseLeave={() => handleManual(0.0, 0.0)}
              className="w-11 h-11 bg-slate-800 hover:bg-sky-600 active:bg-sky-500 rounded-xl font-bold text-sm flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-md"
            >
              ▲ W
            </button>
            <div />
            <button
              onMouseDown={() => handleManual(0.0, 1.0)}
              onMouseUp={() => handleManual(0.0, 0.0)}
              onMouseLeave={() => handleManual(0.0, 0.0)}
              className="w-11 h-11 bg-slate-800 hover:bg-sky-600 active:bg-sky-500 rounded-xl font-bold text-sm flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-md"
            >
              ◀ A
            </button>
            <button
              onMouseDown={() => handleManual(-0.5, 0.0)}
              onMouseUp={() => handleManual(0.0, 0.0)}
              onMouseLeave={() => handleManual(0.0, 0.0)}
              className="w-11 h-11 bg-slate-800 hover:bg-sky-600 active:bg-sky-500 rounded-xl font-bold text-sm flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-md"
            >
              ▼ S
            </button>
            <button
              onMouseDown={() => handleManual(0.0, -1.0)}
              onMouseUp={() => handleManual(0.0, 0.0)}
              onMouseLeave={() => handleManual(0.0, 0.0)}
              className="w-11 h-11 bg-slate-800 hover:bg-sky-600 active:bg-sky-500 rounded-xl font-bold text-sm flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-md"
            >
              ▶ D
            </button>
          </div>
          <div className="text-[11px] text-slate-500 font-mono">Hold buttons for direct velocity override</div>
        </div>
      )}
    </div>
  );
};

// --- Reasoning Message Component ---
const AgentReasoningCard = ({ message }: { message: ChatMessage }) => {
  const [expandedPlan, setExpandedPlan] = useState(false);
  const reasoning = message.reasoning;
  const confidence = reasoning?.confidence ?? 0;
  const confidencePct = Math.round(confidence * 100);

  const getConfidenceBadgeColor = (val: number) => {
    if (val >= 80) return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    if (val >= 50) return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
  };

  return (
    <div className="flex flex-col items-start w-full max-w-[92%] sm:max-w-[85%]">
      {/* Sender Header */}
      <div className="flex items-center gap-2 mb-1 px-1">
        <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-fuchsia-600 to-sky-500 flex items-center justify-center shadow-sm">
          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <span className="text-xs font-semibold text-fuchsia-300">VisionNav AI Engine</span>
        {confidence > 0 && (
          <span
            className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${getConfidenceBadgeColor(
              confidencePct
            )}`}
          >
            {confidencePct}% CONFIDENCE
          </span>
        )}
        <span className="text-[10px] text-slate-500 font-mono">{message.timestamp}</span>
      </div>

      {/* Main Agent Bubble */}
      <div className="w-full bg-slate-900/80 border border-slate-700/60 rounded-2xl rounded-tl-sm p-4 shadow-xl backdrop-blur-md flex flex-col gap-3">
        {/* Error / Safety Alert Banner */}
        {message.status === 'safety_rejected' || message.status === 'error' ? (
          <div className="bg-rose-950/40 border border-rose-500/50 p-3 rounded-xl flex items-start gap-2.5 text-rose-200 text-xs">
            <svg className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <span className="font-bold block text-rose-300 uppercase tracking-wide text-[10px]">
                {message.status === 'safety_rejected' ? 'Safety Filter Triggered' : 'Execution Warning'}
              </span>
              <span>{message.errorMessage || 'Plan rejected due to safety guidelines.'}</span>
            </div>
          </div>
        ) : null}

        {/* Goal / Explanation Banner */}
        {message.explanation && (
          <div className="bg-sky-950/30 border border-sky-500/20 px-3 py-2 rounded-xl text-sky-200 text-xs leading-relaxed">
            <span className="font-semibold text-sky-400 mr-1.5">Action Summary:</span>
            {message.explanation}
          </div>
        )}

        {/* 4-Section Structured Reasoning Grid */}
        {reasoning && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            {/* User Intent */}
            <div className="bg-slate-950/50 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-sky-400 uppercase tracking-wider">
                <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span>User Intent</span>
              </div>
              <p className="text-xs text-slate-200 leading-relaxed">{reasoning.user_intent || 'Direct control command'}</p>
            </div>

            {/* Scene Analysis */}
            <div className="bg-slate-950/50 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-indigo-400 uppercase tracking-wider">
                <svg className="w-3.5 h-3.5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                <span>Scene Analysis</span>
              </div>
              <p className="text-xs text-slate-200 leading-relaxed">{reasoning.scene_analysis || 'Static indoor environment'}</p>
            </div>

            {/* Decision Process */}
            <div className="bg-slate-950/50 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-cyan-400 uppercase tracking-wider">
                <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
                <span>Decision Process</span>
              </div>
              <p className="text-xs text-slate-200 leading-relaxed">{reasoning.decision_process || 'Executing motion primitive'}</p>
            </div>

            {/* Safety Considerations */}
            <div className="bg-amber-950/30 p-3 rounded-xl border border-amber-500/20 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-400 uppercase tracking-wider">
                <svg className="w-3.5 h-3.5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <span>Safety Guardrails</span>
              </div>
              <p className="text-xs text-amber-200 leading-relaxed">{reasoning.safety_considerations || 'Standard obstacle clearance verified'}</p>
            </div>
          </div>
        )}

        {/* Action Plan Accordion */}
        {message.plan && message.plan.length > 0 && (
          <div className="border-t border-slate-800/80 pt-2">
            <button
              onClick={() => setExpandedPlan(!expandedPlan)}
              className="w-full flex items-center justify-between text-xs text-slate-400 hover:text-slate-200 py-1 transition-colors cursor-pointer"
            >
              <span className="font-mono flex items-center gap-1.5">
                <span className="text-fuchsia-400 font-bold">Planned Actions</span> ({message.plan.length} steps)
              </span>
              <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-300 font-mono">
                {expandedPlan ? 'Hide Details ▲' : 'Show Details ▼'}
              </span>
            </button>

            {expandedPlan && (
              <div className="flex flex-col gap-1.5 mt-2">
                {message.plan.map((step) => (
                  <div
                    key={step.step}
                    className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 text-xs flex items-start gap-2.5"
                  >
                    <span className="w-5 h-5 rounded-full bg-slate-800 text-fuchsia-300 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                      {step.step}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono font-semibold text-sky-300">{step.action}</div>
                      {step.expected_result && (
                        <div className="text-[11px] text-slate-400 mt-0.5">{step.expected_result}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// --- User Message Component ---
const UserMessageCard = ({ message }: { message: ChatMessage }) => {
  return (
    <div className="flex flex-col items-end w-full max-w-[85%] sm:max-w-[75%] ml-auto">
      {/* Sender Header */}
      <div className="flex items-center gap-2 mb-1 px-1">
        <span className="text-[10px] text-slate-500 font-mono">{message.timestamp}</span>
        <span className="text-xs font-semibold text-sky-400">Operator</span>
        <div className="w-5 h-5 rounded-full bg-sky-600 flex items-center justify-center shadow-sm">
          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      </div>

      {/* User Bubble */}
      <div className="bg-sky-950/50 border border-sky-500/40 text-sky-100 rounded-2xl rounded-tr-sm px-4 py-3 shadow-lg shadow-sky-950/20 backdrop-blur-sm">
        <p className="text-sm font-medium leading-relaxed">{message.commandText}</p>
      </div>
    </div>
  );
};

// --- Thinking / Processing Bubble ---
const ThinkingIndicator = () => {
  return (
    <div className="flex flex-col items-start w-full max-w-[85%]">
      <div className="flex items-center gap-2 mb-1 px-1">
        <div className="w-5 h-5 rounded-full bg-fuchsia-600 flex items-center justify-center animate-pulse">
          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <span className="text-xs font-semibold text-fuchsia-300">VisionNav AI Engine</span>
        <span className="text-[10px] font-mono text-fuchsia-400 animate-pulse">THINKING...</span>
      </div>

      <div className="bg-slate-900/80 border border-fuchsia-500/30 rounded-2xl rounded-tl-sm p-4 shadow-xl backdrop-blur-md flex items-center gap-3">
        <div className="flex gap-1.5">
          <span className="w-2 h-2 rounded-full bg-fuchsia-400 animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="text-xs text-slate-300 font-mono">Synthesizing visual scene & computing safe navigation trajectory...</span>
      </div>
    </div>
  );
};

// --- Main App Component ---
function App() {
  const [sessionId] = useState(() => {
    const saved = sessionStorage.getItem('visionnav_session_id');
    if (saved) return saved;
    const newId = `session_${Math.random().toString(36).substring(2, 9)}`;
    sessionStorage.setItem('visionnav_session_id', newId);
    return newId;
  });

  // State
  const [context, setContext] = useState<RobotContext | null>(null);
  const [taskState, setTaskState] = useState<TaskStatus | null>(null);
  const [navHistory, setNavHistory] = useState<NavHistory | null>(null);

  // Chat Messages State
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = localStorage.getItem(`visionnav_chat_${sessionId}`);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // ignore JSON errors
    }
    return [];
  });

  const [command, setCommand] = useState('');
  const [isCommanding, setIsCommanding] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat to bottom on new message
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isCommanding]);

  // Persist messages
  useEffect(() => {
    try {
      localStorage.setItem(`visionnav_chat_${sessionId}`, JSON.stringify(messages));
    } catch {
      // storage quota
    }
  }, [messages, sessionId]);

  // Polling logic
  useEffect(() => {
    const poll = async () => {
      try {
        const [resState, resReasoning, resTask, resNav] = await Promise.all([
          fetch(`${API_BASE}/state`),
          fetch(`${API_BASE}/reasoning?session_id=${sessionId}`),
          fetch(`${API_BASE}/current-task?session_id=${sessionId}`),
          fetch(`${API_BASE}/navigation?session_id=${sessionId}`),
        ]);

        if (resState.ok) setContext(await resState.json());

        // Polled reasoning update (in case backend updated outside command submit)
        if (resReasoning.ok) {
          const r: ReasoningBreakdown = await resReasoning.json();
          if (r && Object.keys(r).length > 0 && r.user_intent) {
            setMessages((prev) => {
              // If there are no messages, or the last agent message doesn't match this intent, record it
              const lastAgent = [...prev].reverse().find((m) => m.sender === 'agent');
              if (!lastAgent || lastAgent.reasoning?.user_intent !== r.user_intent) {
                const newMsg: ChatMessage = {
                  id: `polled_${Date.now()}`,
                  sender: 'agent',
                  timestamp: new Date().toLocaleTimeString(),
                  reasoning: r,
                  status: 'success',
                };
                return [...prev, newMsg];
              }
              return prev;
            });
          }
        }

        if (resTask.ok) setTaskState(await resTask.json());
        if (resNav.ok) setNavHistory(await resNav.json());
      } catch (err) {
        console.error('Telemetry polling error:', err);
      }
    };

    const interval = setInterval(poll, 1000);
    poll(); // immediate initial fetch
    return () => clearInterval(interval);
  }, [sessionId]);

  // Actions
  const executeCommand = async (cmdText: string) => {
    const trimmed = cmdText.trim();
    if (!trimmed || isCommanding) return;

    // Append user message immediately
    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString(),
      commandText: trimmed,
    };

    setMessages((prev) => [...prev, userMsg]);
    setCommand('');
    setIsCommanding(true);

    try {
      const res = await fetch(`${API_BASE}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, command: trimmed }),
      });

      if (res.ok) {
        const data: PlannerResponse = await res.json();
        const agentMsg: ChatMessage = {
          id: `agent_${Date.now()}`,
          sender: 'agent',
          timestamp: new Date().toLocaleTimeString(),
          goal: data.goal,
          explanation: data.explanation_for_user,
          reasoning: data.reasoning,
          plan: data.plan,
          status: 'success',
        };
        setMessages((prev) => [...prev, agentMsg]);
      } else {
        const errorData = await res.json().catch(() => ({ detail: 'Command failed' }));
        const isSafety = res.status === 400 || (errorData.detail && errorData.detail.toLowerCase().includes('unsafe'));
        const agentMsg: ChatMessage = {
          id: `agent_err_${Date.now()}`,
          sender: 'agent',
          timestamp: new Date().toLocaleTimeString(),
          status: isSafety ? 'safety_rejected' : 'error',
          errorMessage: errorData.detail || 'Failed to generate a valid plan.',
        };
        setMessages((prev) => [...prev, agentMsg]);
      }
    } catch (err: unknown) {
      const errorStr = err instanceof Error ? err.message : 'Network error communicating with backend API';
      const agentMsg: ChatMessage = {
        id: `agent_err_${Date.now()}`,
        sender: 'agent',
        timestamp: new Date().toLocaleTimeString(),
        status: 'error',
        errorMessage: errorStr,
      };
      setMessages((prev) => [...prev, agentMsg]);
    } finally {
      setIsCommanding(false);
    }
  };

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    executeCommand(command);
  };

  const handleManual = async (linear: number, angular: number) => {
    try {
      await fetch(`${API_BASE}/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ linear_x: linear, angular_z: angular }),
      });
    } catch (err) {
      console.error('Manual control error:', err);
    }
  };

  const handleStop = async () => {
    executeCommand('Stop navigation immediately');
  };

  const handleClearHistory = () => {
    setMessages([]);
    localStorage.removeItem(`visionnav_chat_${sessionId}`);
  };

  const quickPrompts = [
    'Explore the room and map obstacles',
    'Find and navigate to the nearest chair',
    'Return to home dock',
    'Stop navigation immediately',
  ];

  return (
    <div className="h-screen max-h-screen flex flex-col p-4 md:p-6 max-w-[1600px] mx-auto overflow-hidden">
      {/* Header */}
      <header className="flex justify-between items-center pb-3 mb-4 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-500 to-fuchsia-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl md:text-2xl font-black bg-clip-text text-transparent bg-gradient-to-r from-sky-400 via-fuchsia-400 to-indigo-400">
              VisionNav-Sim Cockpit
            </h1>
            <p className="text-[11px] text-slate-400 font-mono">
              Session: <span className="text-slate-300">{sessionId}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-900/80 px-3 py-1.5 rounded-full border border-slate-800 text-xs">
            <div className={`w-2.5 h-2.5 rounded-full ${context ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
            <span className="font-semibold text-slate-300">{context ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
        </div>
      </header>

      {/* Main Grid: Left sidebar (telemetry & controls) + Right (AI Reasoning Chat Window) */}
      <main className="grid grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Column: Camera Feed, Metrics, Navigation/Teleop (compact & scrollable) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-4 overflow-y-auto min-h-0 pr-1">
          <CameraFeedPanel />
          <RobotStatePanel context={context} taskState={taskState} />
          <NavigationAndControlsPanel
            navHistory={navHistory}
            handleManual={handleManual}
            handleStop={handleStop}
          />
        </div>

        {/* Right Column: Interactive AI Reasoning Engine Chat Window */}
        <div className="col-span-12 lg:col-span-8 flex flex-col h-full min-h-0">
          <div className="glass-panel flex-1 flex flex-col min-h-0 overflow-hidden shadow-2xl">
            {/* Chat Window Header */}
            <div className="p-3.5 px-5 bg-slate-900/60 border-b border-slate-800 flex justify-between items-center shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="w-2.5 h-2.5 rounded-full bg-fuchsia-500 animate-pulse" />
                <h2 className="text-sm font-semibold tracking-wide text-slate-100 flex items-center gap-2">
                  <span>AI Reasoning Stream</span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-fuchsia-500/10 text-fuchsia-300 border border-fuchsia-500/20">
                    Ollama Multi-Modal LLM
                  </span>
                </h2>
              </div>

              <div className="flex items-center gap-3">
                {taskState?.active_task && (
                  <span className="text-[11px] bg-emerald-500/10 text-emerald-300 px-2.5 py-1 rounded-md border border-emerald-500/20 font-medium truncate max-w-xs">
                    Active: {taskState.active_task}
                  </span>
                )}
                {messages.length > 0 && (
                  <button
                    onClick={handleClearHistory}
                    className="text-xs text-slate-400 hover:text-rose-400 transition-colors px-2 py-1 rounded hover:bg-rose-500/10 cursor-pointer flex items-center gap-1"
                    title="Clear Conversation History"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    <span>Clear</span>
                  </button>
                )}
              </div>
            </div>

            {/* Chat Message Scrollable Container */}
            <div
              ref={chatContainerRef}
              className="flex-1 overflow-y-auto p-4 md:p-5 flex flex-col gap-4 scroll-smooth min-h-0"
            >
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-6 my-auto">
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-fuchsia-500/20 to-sky-500/20 border border-fuchsia-500/30 flex items-center justify-center mb-3">
                    <svg className="w-7 h-7 text-fuchsia-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <h3 className="text-base font-bold text-slate-200">VisionNav Reasoning Engine Ready</h3>
                  <p className="text-xs text-slate-400 max-w-md mt-1 mb-5">
                    Send a natural language instruction to the robot. The AI will decompose intent, analyze camera perceptions, evaluate safety constraints, and execute motion plans.
                  </p>

                  {/* Quick Starter Chips */}
                  <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                    {quickPrompts.map((prompt, i) => (
                      <button
                        key={i}
                        onClick={() => executeCommand(prompt)}
                        className="text-xs bg-slate-900/80 hover:bg-sky-950/80 border border-slate-700/80 hover:border-sky-500/50 text-slate-300 hover:text-sky-200 px-3 py-1.5 rounded-full transition-all cursor-pointer shadow-sm"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {messages.map((msg) =>
                    msg.sender === 'user' ? (
                      <UserMessageCard key={msg.id} message={msg} />
                    ) : (
                      <AgentReasoningCard key={msg.id} message={msg} />
                    )
                  )}
                  {isCommanding && <ThinkingIndicator />}
                </>
              )}
            </div>

            {/* Quick Prompt Bar (when in chat) */}
            {messages.length > 0 && (
              <div className="px-4 py-1.5 bg-slate-950/40 border-t border-slate-800/60 flex items-center gap-2 overflow-x-auto shrink-0">
                <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 shrink-0">
                  Quick Actions:
                </span>
                {quickPrompts.slice(0, 3).map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => executeCommand(prompt)}
                    disabled={isCommanding}
                    className="text-[11px] whitespace-nowrap bg-slate-900 hover:bg-sky-900/50 text-slate-400 hover:text-sky-200 border border-slate-800 px-2.5 py-0.5 rounded-full transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}

            {/* Integrated Command Input Bar */}
            <div className="p-3.5 bg-slate-950/80 border-t border-slate-800/80 shrink-0">
              <form onSubmit={handleCommand} className="flex gap-2.5">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="Enter command (e.g., 'Navigate to table', 'Explore room', 'Inspect bottle')..."
                    className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all text-slate-100 placeholder-slate-500"
                    disabled={isCommanding}
                  />
                </div>
                <button
                  type="submit"
                  disabled={!command.trim() || isCommanding}
                  className="bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold tracking-wider px-5 py-2.5 rounded-xl transition-all shadow-lg shadow-sky-500/20 cursor-pointer flex items-center gap-1.5 shrink-0"
                >
                  {isCommanding ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>PLANNING...</span>
                    </>
                  ) : (
                    <>
                      <span>EXECUTE</span>
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
