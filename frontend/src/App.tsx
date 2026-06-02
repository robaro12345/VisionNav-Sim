import { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api';

// --- Interfaces ---
interface RobotState {
  position: { x: number; y: number; z: number; frame_id: string };
  orientation: { roll: number; pitch: number; yaw: number };
  battery: number;
  is_moving: boolean;
  velocity_linear: number;
}

interface RobotContext {
  robot_pose: RobotState;
  navigation_status: { state: string; status_text: string; progress: number };
}

interface ReasoningBreakdown {
  user_intent: string;
  scene_analysis: string;
  decision_process: string;
  safety_considerations: string;
  confidence: number;
}

interface TaskStatus {
  active_task: string;
  task_history: any[];
}

interface NavHistory {
  navigation_history: any[];
}

// --- Main App Component ---
function App() {
  const [sessionId] = useState(() => `session_${Math.random().toString(36).substr(2, 9)}`);
  
  // State
  const [context, setContext] = useState<RobotContext | null>(null);
  const [reasoning, setReasoning] = useState<ReasoningBreakdown | null>(null);
  const [taskState, setTaskState] = useState<TaskStatus | null>(null);
  const [navHistory, setNavHistory] = useState<NavHistory | null>(null);
  
  const [command, setCommand] = useState('');
  const [isCommanding, setIsCommanding] = useState(false);

  // Polling logic
  useEffect(() => {
    const poll = async () => {
      try {
        const [resState, resReasoning, resTask, resNav] = await Promise.all([
          fetch(`${API_BASE}/state`),
          fetch(`${API_BASE}/reasoning?session_id=${sessionId}`),
          fetch(`${API_BASE}/current-task?session_id=${sessionId}`),
          fetch(`${API_BASE}/navigation?session_id=${sessionId}`)
        ]);

        if (resState.ok) setContext(await resState.json());
        if (resReasoning.ok) {
          const r = await resReasoning.json();
          if (Object.keys(r).length > 0) setReasoning(r);
        }
        if (resTask.ok) setTaskState(await resTask.json());
        if (resNav.ok) setNavHistory(await resNav.json());
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    const interval = setInterval(poll, 1000);
    poll(); // immediate initial fetch
    return () => clearInterval(interval);
  }, [sessionId]);

  // Actions
  const handleCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || isCommanding) return;
    
    setIsCommanding(true);
    try {
      await fetch(`${API_BASE}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, command })
      });
      setCommand('');
    } catch (err) {
      console.error(err);
    } finally {
      setIsCommanding(false);
    }
  };

  const handleManual = async (linear: number, angular: number) => {
    await fetch(`${API_BASE}/manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ linear_x: linear, angular_z: angular })
    });
  };

  const handleStop = async () => {
    // E-Stop routes through command to ensure safe pipeline cancellation or via a dedicated endpoint. 
    // Since we don't have a dedicated emergency endpoint, we use the command `stop navigation`.
    await fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, command: "Stop navigation immediately" })
    });
  };

  // Sub-components
  const CameraFeedPanel = () => {
    // Add cache buster query string to automatically reload the image periodically
    const [timestamp, setTimestamp] = useState(Date.now());
    
    useEffect(() => {
      const interval = setInterval(() => setTimestamp(Date.now()), 500); // 2FPS update rate
      return () => clearInterval(interval);
    }, []);

    return (
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-xl font-semibold text-fuchsia-400">Live Camera Feed</h2>
        <div className="rounded-xl overflow-hidden border border-slate-700/50 bg-black aspect-video flex items-center justify-center relative">
          <img 
            src={`${API_BASE}/camera/frame.jpg?t=${timestamp}`} 
            alt="Live Camera Feed"
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
              const nextSib = e.currentTarget.nextElementSibling as HTMLElement;
              if (nextSib) nextSib.classList.remove('hidden');
            }}
            onLoad={(e) => {
              e.currentTarget.style.display = 'block';
              const nextSib = e.currentTarget.nextElementSibling as HTMLElement;
              if (nextSib) nextSib.classList.add('hidden');
            }}
          />
          <div className="hidden absolute text-slate-500 font-mono text-sm flex flex-col items-center gap-2">
            <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3" />
            </svg>
            NO SIGNAL
          </div>
        </div>
      </div>
    );
  };

  const RobotStatePanel = () => {
    if (!context) return <div className="glass-panel p-6">Loading state...</div>;
    const { robot_pose, navigation_status } = context;
    
    return (
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-xl font-semibold text-sky-400">System Metrics</h2>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-800/50 p-4 rounded-xl">
            <div className="text-sm text-slate-400">Battery</div>
            <div className="text-2xl font-mono text-emerald-400">{robot_pose.battery}%</div>
          </div>
          <div className="bg-slate-800/50 p-4 rounded-xl">
            <div className="text-sm text-slate-400">Status</div>
            <div className="text-xl font-medium text-sky-300 capitalize">{navigation_status.state}</div>
          </div>
          <div className="bg-slate-800/50 p-4 rounded-xl">
            <div className="text-sm text-slate-400">Speed (m/s)</div>
            <div className="text-xl font-mono text-slate-200">{robot_pose.velocity_linear.toFixed(2)}</div>
          </div>
          <div className="bg-slate-800/50 p-4 rounded-xl">
            <div className="text-sm text-slate-400">Yaw (rad)</div>
            <div className="text-xl font-mono text-slate-200">{robot_pose.orientation.yaw.toFixed(2)}</div>
          </div>
        </div>
        
        <div className="mt-2 text-sm text-slate-400">
          Position: X:{robot_pose.position.x.toFixed(2)} Y:{robot_pose.position.y.toFixed(2)}
        </div>
      </div>
    );
  };

  const ReasoningPanel = () => {
    if (!reasoning) return (
      <div className="glass-panel p-6 flex flex-col gap-4 h-full">
        <h2 className="text-xl font-semibold text-fuchsia-400">AI Reasoning Engine</h2>
        <div className="text-slate-500 italic">Waiting for command...</div>
      </div>
    );
    
    return (
      <div className="glass-panel p-6 flex flex-col gap-4 h-full">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold text-fuchsia-400">AI Reasoning Engine</h2>
          <span className="px-3 py-1 bg-fuchsia-500/20 text-fuchsia-300 rounded-full text-xs font-mono">
            CONFIDENCE: {(reasoning.confidence * 100).toFixed(0)}%
          </span>
        </div>
        
        <div className="flex flex-col gap-3 flex-1 overflow-y-auto">
          <div className="bg-slate-800/40 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">User Intent</span>
            <span className="text-slate-200">{reasoning.user_intent}</span>
          </div>
          <div className="bg-slate-800/40 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">Scene Analysis</span>
            <span className="text-slate-200">{reasoning.scene_analysis}</span>
          </div>
          <div className="bg-slate-800/40 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">Decision Process</span>
            <span className="text-slate-200">{reasoning.decision_process}</span>
          </div>
          <div className="bg-amber-900/20 p-4 rounded-xl border border-amber-700/30">
            <span className="block text-xs font-semibold text-amber-500 mb-1 uppercase tracking-wider">Safety Considerations</span>
            <span className="text-amber-200">{reasoning.safety_considerations}</span>
          </div>
        </div>
      </div>
    );
  };

  const NavigationPanel = () => {
    return (
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-xl font-semibold text-indigo-400">Navigation History</h2>
        <div className="flex flex-col gap-2 overflow-y-auto max-h-64 pr-2">
          {(!navHistory?.navigation_history || navHistory.navigation_history.length === 0) ? (
            <div className="text-slate-500 italic">No history yet.</div>
          ) : (
            [...navHistory.navigation_history].reverse().map((entry, idx) => (
              <div key={idx} className="bg-slate-800/30 p-3 rounded-lg border border-slate-700/30 flex justify-between items-center">
                <div>
                  <div className="text-sm font-medium text-slate-200">{entry.target}</div>
                  <div className="text-xs text-slate-400 mt-1">{new Date(entry.timestamp).toLocaleTimeString()}</div>
                </div>
                <div className={`text-xs px-2 py-1 rounded-md ${entry.result.includes('success') ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                  {entry.result}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    );
  };

  const ManualTeleopPanel = () => {
    return (
      <div className="glass-panel p-6 flex flex-col items-center justify-center gap-6">
        <h2 className="text-xl font-semibold text-slate-300 self-start">Manual Override</h2>
        
        <div className="grid grid-cols-3 gap-2 w-48">
          <div />
          <button 
            onMouseDown={() => handleManual(0.5, 0.0)} 
            onMouseUp={() => handleManual(0.0, 0.0)}
            onMouseLeave={() => handleManual(0.0, 0.0)}
            className="w-14 h-14 bg-slate-800 hover:bg-slate-700 active:bg-sky-600 rounded-xl flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-lg">
            W
          </button>
          <div />
          <button 
            onMouseDown={() => handleManual(0.0, 1.0)} 
            onMouseUp={() => handleManual(0.0, 0.0)}
            onMouseLeave={() => handleManual(0.0, 0.0)}
            className="w-14 h-14 bg-slate-800 hover:bg-slate-700 active:bg-sky-600 rounded-xl flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-lg">
            A
          </button>
          <button 
            onMouseDown={() => handleManual(-0.5, 0.0)} 
            onMouseUp={() => handleManual(0.0, 0.0)}
            onMouseLeave={() => handleManual(0.0, 0.0)}
            className="w-14 h-14 bg-slate-800 hover:bg-slate-700 active:bg-sky-600 rounded-xl flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-lg">
            S
          </button>
          <button 
            onMouseDown={() => handleManual(0.0, -1.0)} 
            onMouseUp={() => handleManual(0.0, 0.0)}
            onMouseLeave={() => handleManual(0.0, 0.0)}
            className="w-14 h-14 bg-slate-800 hover:bg-slate-700 active:bg-sky-600 rounded-xl flex items-center justify-center transition-colors border border-slate-700 cursor-pointer shadow-lg">
            D
          </button>
        </div>

        <button 
          onClick={handleStop}
          className="w-full py-3 mt-2 bg-rose-600/20 hover:bg-rose-600/40 border border-rose-500/50 text-rose-400 hover:text-rose-300 rounded-xl font-bold tracking-widest transition-all cursor-pointer shadow-[0_0_15px_rgba(225,29,72,0.2)] hover:shadow-[0_0_25px_rgba(225,29,72,0.4)]">
          EMERGENCY STOP
        </button>
      </div>
    );
  };

  return (
    <div className="p-8 max-w-7xl mx-auto flex flex-col gap-8 h-screen">
      
      {/* Header */}
      <header className="flex justify-between items-end pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-4xl font-black bg-clip-text text-transparent bg-gradient-to-r from-sky-400 to-fuchsia-500">
            VisionNav-Sim Cockpit
          </h1>
          <p className="text-slate-400 mt-2 font-medium">Session ID: <span className="font-mono text-slate-500">{sessionId}</span></p>
        </div>
        <div className="flex items-center gap-3 bg-slate-900/50 px-4 py-2 rounded-full border border-slate-800">
          <div className={`w-3 h-3 rounded-full animate-pulse ${context ? 'bg-emerald-500' : 'bg-rose-500'}`} />
          <span className="text-sm font-semibold text-slate-300">
            {context ? 'SYSTEM ONLINE' : 'CONNECTING...'}
          </span>
        </div>
      </header>

      {/* Main Grid */}
      <main className="grid grid-cols-12 gap-8 flex-1 min-h-0">
        
        {/* Left Column (Metrics, Nav, Teleop) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-8">
          <CameraFeedPanel />
          <RobotStatePanel />
          <NavigationPanel />
          <ManualTeleopPanel />
        </div>

        {/* Right Column (Reasoning & Console) */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-8">
          
          <div className="flex-1 min-h-0">
            <ReasoningPanel />
          </div>
          
          {/* Command Console */}
          <div className="glass-panel p-6 shrink-0">
            <h2 className="text-xl font-semibold text-emerald-400 mb-4">Command Terminal</h2>
            
            {taskState?.active_task && (
              <div className="mb-4 text-sm bg-emerald-500/10 text-emerald-300 px-4 py-2 rounded-lg border border-emerald-500/20 inline-block">
                Active Task: {taskState.active_task}
              </div>
            )}

            <form onSubmit={handleCommand} className="flex gap-3">
              <input
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="Enter a natural language command..."
                className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-5 py-4 text-lg focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all text-slate-100 placeholder-slate-600"
                disabled={isCommanding}
              />
              <button
                type="submit"
                disabled={!command.trim() || isCommanding}
                className="bg-sky-500 hover:bg-sky-400 disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold px-8 rounded-xl transition-colors cursor-pointer"
              >
                {isCommanding ? 'PROCESSING...' : 'EXECUTE'}
              </button>
            </form>
          </div>

        </div>
      </main>
    </div>
  );
}

export default App;
