"use client";

import { useState, useEffect, useRef } from "react";
import { Search, Activity, Globe, Wifi, Server, Terminal, ShieldCheck, Play, Square, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { runChecks } from "@/lib/api";
import { MonitorChart } from "@/components/MonitorChart";
import { cn } from "@/lib/utils";

const HISTORY_LIMIT = 180; // 180 seconds as requested

export default function Dashboard() {
  const [target, setTarget] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Monitor state
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [monitorData, setMonitorData] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const handleCheck = async () => {
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      const data = await runChecks(target);
      setResults(data);
    } catch (err) {
      setError("Failed to fetch diagnostic data. Is the backend running?");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const startMonitor = () => {
    if (!target) return;
    if (wsRef.current) wsRef.current.close();

    setMonitorData([]);
    setIsMonitoring(true);

    // Using localhost:8000 for simplicity in this dev environment
    const wsUrl = `ws://localhost:8000/ws/monitor/${target}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMonitorData(prev => {
        const newData = [...prev, data];
        if (newData.length > HISTORY_LIMIT) {
          return newData.slice(newData.length - HISTORY_LIMIT);
        }
        return newData;
      });
    };

    ws.onerror = (event) => {
      console.error("WebSocket Error:", event);
      setError("STREAM_INTERRUPT: WR_PROTOCOL_ERROR_0x1. Ensure backend is operational and system 'ping' binaries are installed.");
      stopMonitor();
    };

    ws.onclose = (event) => {
      if (!event.wasClean && event.code !== 1000) {
        setError(`STREAM_TERMINATED: ERROR_CODE_${event.code}. ${event.reason || "Ping utility might be missing or permissions denied."}`);
      }
      setIsMonitoring(false);
    };
  };

  const stopMonitor = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsMonitoring(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === "ok" || status === "open") {
      return <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border-emerald-500/20">Active</Badge>;
    }
    return <Badge variant="destructive">Failed</Badge>;
  };

  return (
    <div className="min-h-screen bg-[#050505] text-neutral-100 selection:bg-lime-500/30 overflow-x-hidden">
      {/* Cyberpunk Grid Background */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div 
          className="absolute inset-0 opacity-[0.15]" 
          style={{ 
            backgroundImage: `linear-gradient(to right, #4ade80 1px, transparent 1px), linear-gradient(to bottom, #4ade80 1px, transparent 1px)`,
            backgroundSize: '40px 40px'
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#050505] via-transparent to-transparent" />
        
        {/* Animated Glows */}
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-lime-500/10 blur-[120px] rounded-full animate-pulse" />
        <div className="absolute bottom-[20%] right-[-5%] w-[30%] h-[30%] bg-purple-600/10 blur-[100px] rounded-full animate-bounce duration-[10000ms]" />
        
        {/* Scanlines */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.1)_50%),linear-gradient(90deg,rgba(255,0,0,0.03),rgba(0,255,0,0.01),rgba(0,0,255,0.03))] z-10 pointer-events-none bg-[length:100%_2px,3px_100%]" />
      </div>

      <main className="relative z-10 max-w-6xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="flex flex-col gap-2 mb-12">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-lime-500 flex items-center justify-center shadow-[0_0_20px_rgba(163,230,53,0.4)] border border-lime-400/50 relative overflow-hidden group">
              <Activity className="w-7 h-7 text-black relative z-10" />
              <div className="absolute inset-0 bg-white/20 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-500" />
            </div>
            <div>
              <h1 className="text-4xl font-black tracking-tighter uppercase italic text-lime-400 [text-shadow:0_0_10px_rgba(163,230,53,0.5)]">
                NetHealth <span className="text-white">OS v2.0</span>
              </h1>
              <div className="h-1 w-full bg-lime-500/20 mt-1 relative overflow-hidden">
                <div className="absolute inset-0 bg-lime-400 translate-x-[-100%] animate-[shimmer_3s_infinite]" />
              </div>
            </div>
          </div>
          <p className="text-neutral-400 max-w-xl font-mono text-sm mt-4 border-l-2 border-lime-500/50 pl-4 py-1">
            NETWORK DIAGNOSTICS KERNEL // STATUS: <span className="text-lime-400 animate-pulse">READY</span>
            <br />
            ENTER TARGET HANDLER OR IP TO INITIATE SEQUENCE.
          </p>
        </div>

        {/* Search Bar */}
        <Card className="mb-12 bg-black/60 border-lime-500/30 backdrop-blur-md shadow-[0_0_30px_rgba(0,0,0,0.5)] border-t-lime-500/50 overflow-hidden relative">
          <div className="absolute top-0 right-0 p-1 text-[10px] font-mono text-lime-500/40 uppercase">input_handler_v0.9</div>
          <CardContent className="p-8">
            <div className="flex flex-col md:flex-row gap-6">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-lime-500/50" />
                <Input
                  placeholder="HOSTNAME OR IP ADDRESS..."
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCheck()}
                  className="pl-12 h-14 bg-black/40 border-lime-500/20 focus:border-lime-500/60 focus:ring-lime-500/20 text-lime-100 font-mono placeholder:text-neutral-700 transition-all uppercase tracking-widest text-lg"
                />
              </div>
              <div className="flex gap-3">
                <Button
                  onClick={handleCheck}
                  disabled={loading || isMonitoring || !target}
                  className="h-14 px-8 bg-lime-500 hover:bg-lime-400 text-black font-black uppercase tracking-tighter transition-all duration-300 disabled:opacity-30 disabled:grayscale shadow-[0_0_15px_rgba(163,230,53,0.3)] hover:shadow-[0_0_25px_rgba(163,230,53,0.5)] rounded-sm"
                >
                  {loading ? "INITIALIZING..." : "RUN_SUITE"}
                </Button>
                <Button
                  variant="outline"
                  onClick={isMonitoring ? stopMonitor : startMonitor}
                  disabled={loading || !target}
                  className={cn(
                    "h-14 px-8 border-lime-500/30 font-bold uppercase tracking-widest transition-all duration-300 rounded-sm",
                    isMonitoring 
                      ? "bg-red-500/20 text-red-500 border-red-500/40 hover:bg-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.2)]" 
                      : "bg-black/40 text-lime-400 hover:bg-lime-500/10 border-lime-500/30"
                  )}
                >
                  {isMonitoring ? (
                    <><Square className="w-5 h-5 mr-2 fill-current" /> STOP_MONITOR</>
                  ) : (
                    <><Play className="w-5 h-5 mr-2 fill-current" /> LIVE_STREAM</>
                  )}
                </Button>
              </div>
            </div>
            {error && (
              <div className="mt-6 p-4 bg-red-500/10 border border-red-500/30 rounded-sm flex items-start gap-3 animate-in fade-in slide-in-from-top-1">
                <Terminal className="w-5 h-5 text-red-500 mt-0.5" />
                <div>
                  <p className="text-red-500 text-xs font-black uppercase tracking-widest">System Error Detect</p>
                  <p className="text-red-400 text-sm font-mono mt-1">{error}</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {loading && (
          <div className="flex flex-col items-center justify-center py-24 gap-6">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 border-2 border-lime-500/10 rounded-full" />
              <div className="absolute inset-0 border-t-2 border-lime-400 rounded-full animate-spin" />
              <div className="absolute inset-4 border-r-2 border-purple-500 rounded-full animate-[spin_1.5s_linear_infinite_reverse]" />
              <Activity className="absolute inset-0 m-auto w-8 h-8 text-lime-400 animate-pulse" />
            </div>
            <div className="text-center">
              <p className="text-lime-400 font-mono tracking-[0.3em] uppercase text-sm">Intercepting Packets</p>
              <p className="text-neutral-600 font-mono text-xs mt-2 uppercase">Please wait for protocol handshake...</p>
            </div>
          </div>
        )}

        {/* Monitor View */}
        {(isMonitoring || monitorData.length > 0) && (
          <Card className="mb-12 bg-black/40 border-lime-500/20 overflow-hidden animate-in fade-in slide-in-from-top-8 duration-700 backdrop-blur-sm relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-lime-500/50 to-transparent" />
            <CardHeader className="border-b border-white/5 flex flex-row items-center justify-between p-6">
              <div>
                <div className="flex items-center gap-3">
                  <Timer className="w-6 h-6 text-lime-400" />
                  <CardTitle className="text-xl uppercase tracking-widest italic font-black text-white">
                    Latency_Telemetry
                  </CardTitle>
                </div>
                <CardDescription className="text-neutral-500 font-mono mt-1">
                  TRACKING_TARGET: <span className="text-lime-400">{target}</span> // HISTORY: 180S
                </CardDescription>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Badge variant="outline" className={cn(
                  "px-3 py-1 font-mono text-[10px]",
                  isMonitoring ? "bg-lime-500 text-black border-none ring-4 ring-lime-500/20" : "bg-neutral-800 text-neutral-500 border-neutral-700"
                )}>
                  {isMonitoring ? "STREAM_ACTIVE" : "STREAM_PAUSED"}
                </Badge>
                {monitorData.length > 0 && (
                  <span className="text-[10px] font-mono text-neutral-600 uppercase">
                    last_val: {monitorData[monitorData.length-1].latency?.toFixed(1) || '0.0'}ms
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-8">
              <MonitorChart data={monitorData} />
            </CardContent>
          </Card>
        )}

        {results && !loading && !isMonitoring && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 animate-in fade-in slide-in-from-bottom-8 duration-1000">
            {/* Ping Check */}
            <Card className="bg-black/60 border-lime-500/20 group hover:border-lime-500/50 transition-all duration-500 shadow-xl overflow-hidden relative">
              <div className="absolute top-0 right-0 w-16 h-16 bg-lime-500/5 rotate-45 translate-x-10 translate-y-[-10px] pointer-events-none" />
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-3 rounded-lg bg-lime-500/10 text-lime-400 group-hover:bg-lime-500/20 transition-colors">
                    <Wifi className="w-6 h-6" />
                  </div>
                  <StatusIcon status={results.ping.status} />
                </div>
                <CardTitle className="text-sm uppercase tracking-widest text-neutral-400">Network Latency</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-baseline gap-2">
                  <span className="text-5xl font-black italic tracking-tighter text-white">
                    {results.ping.avg_ms?.toFixed(1) || "---"}
                  </span>
                  <span className="text-lime-500 font-mono text-sm font-bold uppercase">ms</span>
                </div>
                <div className="mt-6 flex items-center justify-between text-[10px] font-mono text-neutral-600 uppercase mb-1">
                  <span>Packet RTT Stability</span>
                  <span>{results.ping.status === "ok" ? "Nominal" : "Irregular"}</span>
                </div>
                <div className="h-1.5 w-full bg-neutral-900 rounded-full overflow-hidden border border-white/5">
                  <div 
                    className="h-full bg-lime-500 shadow-[0_0_8px_rgba(163,230,53,0.6)] transition-all duration-1000" 
                    style={{ width: `${Math.min((results.ping.avg_ms || 0) / 2, 100)}%` }}
                  />
                </div>
              </CardContent>
            </Card>

            {/* DNS Check */}
            <Card className="bg-black/60 border-lime-500/20 group hover:border-purple-500/50 transition-all duration-500 shadow-xl overflow-hidden relative">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-3 rounded-lg bg-purple-500/10 text-purple-400 group-hover:bg-purple-500/20 transition-colors">
                    <Globe className="w-6 h-6" />
                  </div>
                  <StatusIcon status={results.dns.status} />
                </div>
                <CardTitle className="text-sm uppercase tracking-widest text-neutral-400">DNS Resolution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="mt-2 group-hover:translate-x-1 transition-transform">
                  <div className="text-xs font-mono bg-neutral-900 border border-white/5 p-3 rounded text-neutral-300 break-all leading-relaxed shadow-inner">
                    <span className="text-purple-500 mr-2 opacity-50">&gt;</span>
                    {results.dns.addresses?.[0] || "NULL_ENTRY"}
                  </div>
                </div>
                <div className="mt-4 text-[10px] font-mono text-neutral-600 uppercase border-t border-white/5 pt-3">
                  RESOLVER: {results.dns.status === "ok" ? "LOCAL_UNBOUND" : "INVALID"}
                </div>
              </CardContent>
            </Card>

            {/* HTTP Check */}
            <Card className="bg-black/60 border-lime-500/20 group hover:border-yellow-500/50 transition-all duration-500 shadow-xl overflow-hidden relative">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-3 rounded-lg bg-yellow-500/10 text-yellow-500 group-hover:bg-yellow-500/20 transition-colors">
                    <Server className="w-6 h-6" />
                  </div>
                  <StatusIcon status={results.http.status} />
                </div>
                <CardTitle className="text-sm uppercase tracking-widest text-neutral-400">Handshake Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-baseline gap-3">
                  <span className={cn(
                    "text-5xl font-black italic tracking-tighter",
                    results.http.status_code < 400 ? "text-white" : "text-yellow-500"
                  )}>
                    {results.http.status_code || "---"}
                  </span>
                  <span className="text-neutral-500 font-mono text-xs uppercase font-bold tracking-widest">
                    {results.http.status_msg || "Unknown"}
                  </span>
                </div>
                <div className="mt-6 flex gap-1">
                  {[...Array(5)].map((_, i) => (
                    <div 
                      key={i} 
                      className={cn(
                        "h-1 flex-1 rounded-full",
                        results.http.status === "ok" ? "bg-yellow-500/40" : "bg-neutral-800"
                      )} 
                    />
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Port Check */}
            <Card className="bg-black/60 border-lime-500/20 group hover:border-lime-400/50 transition-all duration-500 shadow-xl overflow-hidden relative">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-3 rounded-lg bg-lime-500/10 text-lime-400 group-hover:bg-lime-500/20 transition-colors">
                    <ShieldCheck className="w-6 h-6" />
                  </div>
                  <StatusIcon status={results.port.status} />
                </div>
                <CardTitle className="text-sm uppercase tracking-widest text-neutral-400">Logic Gates</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2 mt-1">
                  {results.port.results.map((p: any) => (
                    <div 
                      key={p.port} 
                      className={cn(
                        "px-2 py-1 text-[10px] font-mono border rounded flex items-center gap-1.5 transition-all duration-300",
                        p.status === "open" 
                          ? "bg-lime-500/10 text-lime-400 border-lime-500/30 scale-100 shadow-[0_0_8px_rgba(163,230,53,0.1)]" 
                          : "bg-neutral-900 text-neutral-700 border-white/5 opacity-50 grayscale"
                      )}
                    >
                      <div className={cn("w-1.5 h-1.5 rounded-full", p.status === "open" ? "bg-lime-400 animate-pulse" : "bg-neutral-800")} />
                      {p.port}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Terminal Details */}
            <Card className="md:col-span-2 lg:col-span-4 bg-black/60 border-lime-500/20 overflow-hidden relative backdrop-blur-md">
              <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-lime-500/30 to-transparent" />
              <CardHeader className="border-b border-white/5 bg-white/5 py-4">
                <div className="flex items-center gap-3">
                  <Terminal className="w-5 h-5 text-lime-400" />
                  <CardTitle className="text-xs uppercase tracking-[0.4em] font-black text-white">Console_Debug_Output</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/10">
                  <div className="p-8">
                    <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-500/60 mb-6 flex items-center gap-2">
                       <div className="w-1 h-3 bg-lime-500" /> Target Meta
                    </h4>
                    <dl className="space-y-6 font-mono">
                      <div>
                        <dt className="text-[10px] text-neutral-500 uppercase mb-1">Hostname Binding</dt>
                        <dd className="text-lg font-bold text-white selection:bg-purple-500/40">{target}</dd>
                      </div>
                      <div>
                        <dt className="text-[10px] text-neutral-500 uppercase mb-1">IPv4 Entrypoint</dt>
                        <dd className="text-sm font-bold text-lime-400">{results.dns.addresses?.[0] || 'UNRESOLVED'}</dd>
                      </div>
                    </dl>
                  </div>
                  <div className="p-8 bg-neutral-900/10">
                    <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-500/60 mb-6 flex items-center gap-2">
                      <div className="w-1 h-3 bg-lime-500" /> Cycle Metrics
                    </h4>
                    <dl className="space-y-6 font-mono">
                      <div className="flex items-center justify-between">
                        <dt className="text-[10px] text-neutral-500 uppercase">DNS Response</dt>
                        <dd className="text-sm border-b border-dashed border-white/10 pb-0.5">{results.dns.time_ms?.toFixed(2)} ms</dd>
                      </div>
                      <div className="flex items-center justify-between">
                        <dt className="text-[10px] text-neutral-500 uppercase">Handshake Latency</dt>
                        <dd className="text-sm border-b border-dashed border-white/10 pb-0.5">{results.http.response_time?.toFixed(2)}s</dd>
                      </div>
                    </dl>
                  </div>
                  <div className="p-8">
                    <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-500/60 mb-6 flex items-center gap-2">
                      <div className="w-1 h-3 bg-lime-500" /> Kernel Environment
                    </h4>
                    <p className="text-xs text-neutral-500 font-mono leading-relaxed italic">
                      SYSTEM_STATUS: <span className="text-lime-400">STABLE</span><br />
                      UPSTREAM_NODES: <span className="text-neutral-300">CALIBRATED</span><br />
                      PERFORMANCE_TIER: <span className="text-purple-400">ULTRA</span><br /><br />
                      No hardware faults detected in network stack.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {!results && !loading && !isMonitoring && monitorData.length === 0 && (
          <div className="py-24 text-center border border-dashed border-lime-500/20 rounded-xl bg-black/40 backdrop-blur-sm group hover:border-lime-500/40 transition-all duration-700">
            <div className="mx-auto w-16 h-16 rounded-full bg-lime-500/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-500 relative">
               <div className="absolute inset-0 rounded-full border border-lime-500/10 animate-ping group-hover:animate-none scale-150 rotate-45" />
              <ShieldCheck className="w-8 h-8 text-lime-500/40" />
            </div>
            <h3 className="text-xl font-black text-white uppercase tracking-[0.2em] italic">No Active Uplink</h3>
            <p className="text-neutral-500 font-mono text-xs max-w-xs mx-auto mt-4 uppercase tracking-widest leading-loose">
              Initiate diagnostic sequence or establish live telemetry stream above.
            </p>
          </div>
        )}
      </main>

      {/* Decorative Blur Background fixed position */}
      <style jsx global>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
}