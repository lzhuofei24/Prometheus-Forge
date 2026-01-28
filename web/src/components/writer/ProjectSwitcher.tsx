import { useState, useRef, useEffect } from 'react';
import { Button } from '../ui/button';
import { ChevronDown, BookOpen, Plus, Loader2, Upload, Trash2, Download } from 'lucide-react';
import { useCreateNovel, useNovels } from '../../hooks/useNovels';
import { novelsApi } from '../../api/services';
import { logger } from '../../utils/logger';
import { cn } from '../../lib/utils';
import type { Novel } from '../../types';

interface ProjectSwitcherProps {
  novels: Novel[];
  currentNovelId: string | null;
  onNovelChange: (novelId: string | null) => void;
  isLoading?: boolean;
}

export default function ProjectSwitcher({
  novels,
  currentNovelId,
  onNovelChange,
  isLoading,
}: ProjectSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const createNovelMutation = useCreateNovel();
  const { refetch: refetchNovels } = useNovels();

  const currentNovel = novels.find((n) => n.id === currentNovelId);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleCreateNovel = async () => {
    logger.action('ProjectSwitcher', 'User clicked Create Novel button');
    const name = prompt('输入新小说名称:');
    if (!name) {
      logger.info('ProjectSwitcher', 'User cancelled novel creation');
      return;
    }

    try {
      logger.action('ProjectSwitcher', 'Creating novel', { title: name });
      const novel = await createNovelMutation.mutateAsync({ title: name });
      logger.info('ProjectSwitcher', 'Novel created successfully', { novelId: novel.id, title: novel.title });
      onNovelChange(novel.id);
      setIsOpen(false);
    } catch (error) {
      logger.error('ProjectSwitcher', 'Failed to create novel', { error, title: name });
      console.error('创建小说失败:', error);
      alert('创建小说失败: ' + (error instanceof Error ? error.message : String(error)));
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!file.name.endsWith('.txt')) {
      alert('只支持 .txt 文件');
      return;
    }

    const title = prompt('输入小说名称:');
    if (!title) {
      logger.info('ProjectSwitcher', 'User cancelled novel import');
      return;
    }

    setIsImporting(true);
    logger.action('ProjectSwitcher', 'User started importing novel', { fileName: file.name, title });

    try {
      const result = await novelsApi.import(file, title);
      logger.info('ProjectSwitcher', 'Novel imported successfully', {
        novelId: result.novel_id,
        title: result.novel_title,
        chaptersCount: result.chapters_count,
      });
      alert(`导入成功！共 ${result.chapters_count} 个章节`);
      await refetchNovels();
      onNovelChange(result.novel_id);
      setIsOpen(false);
    } catch (error) {
      logger.error('ProjectSwitcher', 'Failed to import novel', { error, fileName: file.name });
      console.error('导入小说失败:', error);
      alert('导入失败: ' + (error instanceof Error ? error.message : String(error)));
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDeleteNovel = async (novelId: string, novelTitle: string) => {
    if (!confirm(`确定要删除小说《${novelTitle}》吗？此操作将删除该小说的所有章节和数据，且不可恢复。`)) {
      return;
    }

    setIsDeleting(true);
    logger.action('ProjectSwitcher', 'User started deleting novel', { novelId, title: novelTitle });

    try {
      await novelsApi.delete(novelId);
      logger.info('ProjectSwitcher', 'Novel deleted successfully', { novelId, title: novelTitle });
      alert('删除成功');
      await refetchNovels();
      if (currentNovelId === novelId) {
        onNovelChange(null);
      }
      setIsOpen(false);
    } catch (error) {
      logger.error('ProjectSwitcher', 'Failed to delete novel', { error, novelId, title: novelTitle });
      console.error('删除小说失败:', error);
      alert('删除失败: ' + (error instanceof Error ? error.message : String(error)));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleExportNovel = async (novelId: string, novelTitle: string) => {
    setIsExporting(true);
    logger.action('ProjectSwitcher', 'User started exporting novel', { novelId, title: novelTitle });

    try {
      await novelsApi.export(novelId, novelTitle);
      logger.info('ProjectSwitcher', 'Novel exported successfully', { novelId, title: novelTitle });
    } catch (error) {
      logger.error('ProjectSwitcher', 'Failed to export novel', { error, novelId, title: novelTitle });
      console.error('导出小说失败:', error);
      alert('导出失败: ' + (error instanceof Error ? error.message : String(error)));
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        className="w-full justify-between"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
      >
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4" />
          <span className="font-medium">
            {isLoading ? '加载中...' : currentNovel?.title || '选择小说'}
          </span>
        </div>
        <ChevronDown className="w-4 h-4" />
      </Button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt"
        className="hidden"
        onChange={handleFileChange}
      />
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-zinc-200 rounded-md shadow-lg z-10 max-h-64 overflow-auto">
          <div className="p-1">
            <button
              className="w-full text-left px-3 py-2 text-sm hover:bg-zinc-100 rounded-md flex items-center gap-2"
              onClick={handleCreateNovel}
              disabled={createNovelMutation.isPending}
            >
              {createNovelMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              新建小说
            </button>
            <button
              className="w-full text-left px-3 py-2 text-sm hover:bg-zinc-100 rounded-md flex items-center gap-2 mt-1"
              onClick={handleImportClick}
              disabled={isImporting}
            >
              {isImporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              导入小说 (TXT)
            </button>
            {novels.length > 0 && <div className="border-t border-zinc-200 my-1" />}
            {novels.length === 0 && !isLoading && (
              <div className="px-3 py-2 text-sm text-zinc-500 text-center">
                暂无小说，请先创建
              </div>
            )}
            {novels.map((novel) => (
              <div
                key={novel.id}
                className={cn(
                  'group flex items-center justify-between px-3 py-2 text-sm hover:bg-zinc-100 rounded-md',
                  currentNovelId === novel.id && 'bg-indigo-50'
                )}
              >
                <button
                  className={cn(
                    'flex-1 text-left',
                    currentNovelId === novel.id && 'text-indigo-900'
                  )}
                  onClick={() => {
                    logger.action('ProjectSwitcher', 'User selected novel', { novelId: novel.id, title: novel.title });
                    onNovelChange(novel.id);
                    setIsOpen(false);
                  }}
                >
                  {novel.title}
                </button>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    className="p-1 hover:bg-zinc-200 rounded text-zinc-600 hover:text-zinc-900"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleExportNovel(novel.id, novel.title);
                    }}
                    disabled={isExporting}
                    title="导出为TXT"
                  >
                    {isExporting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Download className="w-3.5 h-3.5" />
                    )}
                  </button>
                  <button
                    className="p-1 hover:bg-red-100 rounded text-zinc-600 hover:text-red-600"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteNovel(novel.id, novel.title);
                    }}
                    disabled={isDeleting}
                    title="删除小说"
                  >
                    {isDeleting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
