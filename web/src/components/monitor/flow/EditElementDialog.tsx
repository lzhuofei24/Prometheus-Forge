import { useState, useEffect } from 'react';
import { Button } from '../../ui/button';
import { cn } from '../../../lib/utils';

export type EditData = {
  id: string;
  type: 'edge' | 'node';
  label: string;
  edgeColor?: 'default' | 'success' | 'warning';
  edgePattern?: 'solid' | 'dashed';
  animated?: boolean;
};

interface EditElementDialogProps {
  isOpen: boolean;
  onClose: () => void;
  data: EditData | null;
  onSave: (data: EditData) => void;
  /** 删除当前元素（仅连线时可用） */
  onDelete?: (data: EditData) => void;
}

export function EditElementDialog({ isOpen, onClose, data, onSave, onDelete }: EditElementDialogProps) {
  const [label, setLabel] = useState('');
  const [edgeColor, setEdgeColor] = useState<'default' | 'success' | 'warning'>('default');
  const [edgePattern, setEdgePattern] = useState<'solid' | 'dashed'>('solid');
  const [animated, setAnimated] = useState(true);

  useEffect(() => {
    if (data) {
      setLabel(data.label || '');
      setEdgeColor(data.edgeColor ?? 'default');
      setEdgePattern(data.edgePattern ?? 'solid');
      setAnimated(data.animated ?? true);
    }
  }, [data]);

  const handleSave = () => {
    if (!data) return;
    onSave({
      ...data,
      label,
      edgeColor,
      edgePattern,
      animated,
    });
    onClose();
  };

  const handleDelete = () => {
    if (!data) return;
    onDelete?.(data);
    onClose();
  };

  if (!data) return null;
  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} aria-hidden />
      <div className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-[425px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">
          Edit {data.type === 'edge' ? 'Connection' : 'Decision'}
        </h2>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <label htmlFor="edit-dialog-label" className="text-right text-sm text-zinc-400">
              Label
            </label>
            <input
              id="edit-dialog-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="col-span-3 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              placeholder={data.type === 'edge' ? 'e.g. Yes, Score < 60' : 'e.g. Is Safe?'}
            />
          </div>

          {data.type === 'edge' && (
            <>
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right text-sm text-zinc-400">Style</span>
                <div className="col-span-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => setEdgeColor('default')}
                    className={cn(
                      'h-6 w-6 rounded-full border-2 bg-zinc-500',
                      edgeColor === 'default' ? 'border-white' : 'border-transparent'
                    )}
                    title="Default (Gray)"
                  />
                  <button
                    type="button"
                    onClick={() => setEdgeColor('success')}
                    className={cn(
                      'h-6 w-6 rounded-full border-2 bg-emerald-500',
                      edgeColor === 'success' ? 'border-white' : 'border-transparent'
                    )}
                    title="Success (Green)"
                  />
                  <button
                    type="button"
                    onClick={() => setEdgeColor('warning')}
                    className={cn(
                      'h-6 w-6 rounded-full border-2 bg-amber-500',
                      edgeColor === 'warning' ? 'border-white' : 'border-transparent'
                    )}
                    title="Warning (Orange)"
                  />
                </div>
              </div>

              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right text-sm text-zinc-400">Pattern</span>
                <div className="col-span-3 flex gap-2">
                  <Button
                    size="sm"
                    variant={edgePattern === 'solid' ? 'secondary' : 'outline'}
                    onClick={() => setEdgePattern('solid')}
                    className="h-7 text-xs"
                  >
                    Solid
                  </Button>
                  <Button
                    size="sm"
                    variant={edgePattern === 'dashed' ? 'secondary' : 'outline'}
                    onClick={() => setEdgePattern('dashed')}
                    className="h-7 text-xs"
                  >
                    Dashed
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right text-sm text-zinc-400">Effect</span>
                <div className="col-span-3 flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="edit-dialog-animated"
                    checked={animated}
                    onChange={(e) => setAnimated(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="edit-dialog-animated" className="font-normal text-zinc-300">
                    Animated
                  </label>
                </div>
              </div>
            </>
          )}
        </div>
        <div className="mt-6 flex items-center justify-between gap-2">
          <div>
            {data.type === 'edge' && onDelete && (
              <Button
                variant="outline"
                onClick={handleDelete}
                className="border-red-500/50 text-red-400 hover:bg-red-500/10"
              >
                Delete Connection
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={onClose}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancel
            </Button>
            <Button onClick={handleSave} className="bg-indigo-600 text-white hover:bg-indigo-700">
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
