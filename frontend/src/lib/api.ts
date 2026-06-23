const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function runChecks(target: string) {
  const res = await fetch(`${API_BASE}/check/${target}`);
  if (!res.ok) throw new Error("Failed to run checks");
  return res.json();
}

export async function getTraceroute(target: string) {
  const res = await fetch(`${API_BASE}/traceroute/${target}`);
  if (!res.ok) throw new Error("Failed to run traceroute");
  return res.json();
}

export async function runPortCheck(target: string, ports?: string) {
  const url = ports ? `${API_BASE}/port/${target}?ports=${ports}` : `${API_BASE}/port/${target}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to run port check");
  return res.json();
}
