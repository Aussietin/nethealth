"use client";

import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";

interface MonitorChartProps {
  data: Array<{
    timestamp: string;
    latency: number | null;
  }>;
}

export function MonitorChart({ data }: MonitorChartProps) {
  // Filter out null latency for the graph to avoid breaks, 
  // though recharts handles it ok-ish.
  const chartData = data.map(d => ({
    ...d,
    latency: d.latency ?? 0
  }));

  return (
    <div className="w-full h-[300px] mt-4">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
          <XAxis 
            dataKey="timestamp" 
            stroke="#666" 
            fontSize={12} 
            tickLine={false} 
            axisLine={false}
            interval={Math.floor(data.length / 6)}
          />
          <YAxis 
            stroke="#666" 
            fontSize={12} 
            tickLine={false} 
            axisLine={false}
            tickFormatter={(value) => `${value}ms`}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: '#050505', 
              borderColor: 'oklch(0.85 0.2 145 / 0.3)',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#fff',
              borderWidth: '1px'
            }}
            itemStyle={{ color: 'oklch(0.85 0.2 145)' }}
          />
          <Line 
            type="monotone" 
            dataKey="latency" 
            stroke="oklch(0.85 0.2 145)" 
            strokeWidth={3} 
            dot={false}
            animationDuration={300}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
