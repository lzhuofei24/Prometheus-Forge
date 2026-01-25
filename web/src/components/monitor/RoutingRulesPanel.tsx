import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { Route } from 'lucide-react';

const ROUTING_RULES = [
  { from: 'Architect', to: 'Writer', condition: '—' },
  { from: 'Writer', to: 'Censor', condition: '—' },
  { from: 'Censor', to: 'Critic', condition: 'Pass' },
  { from: 'Censor', to: 'End', condition: 'Block' },
  { from: 'Critic', to: 'Media & Knowledge', condition: 'Score ≥ 75' },
  { from: 'Critic', to: 'Writer', condition: 'Score < 75' },
  { from: 'Media', to: '—', condition: 'End' },
  { from: 'Knowledge', to: '—', condition: 'End' },
];

export function RoutingRulesPanel() {
  return (
    <Card className="h-full min-h-0 flex flex-col bg-zinc-900/50 backdrop-blur-sm border border-zinc-700/50">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center gap-2">
          <Route className="w-4 h-4 text-indigo-400" />
          <CardTitle className="text-sm font-semibold text-zinc-100">
            路由规则
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-auto px-4 pb-4 pt-0">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-700/50 hover:bg-transparent">
              <TableHead className="text-xs text-zinc-400 h-8">From</TableHead>
              <TableHead className="text-xs text-zinc-400 h-8">To</TableHead>
              <TableHead className="text-xs text-zinc-400 h-8">Condition</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROUTING_RULES.map((row, i) => (
              <TableRow
                key={i}
                className="border-zinc-700/30 text-zinc-300 hover:bg-zinc-800/30"
              >
                <TableCell className="text-xs py-1.5">
                  {row.from}
                </TableCell>
                <TableCell className="text-xs py-1.5">
                  {row.to}
                </TableCell>
                <TableCell className="text-xs py-1.5 text-zinc-400">
                  {row.condition}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
