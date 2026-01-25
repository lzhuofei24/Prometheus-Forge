import { useState, useEffect, useMemo } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useWorkflowState, useWorkflowTrace, useStartWorkflow } from '../hooks/useWorkflow';
import { useNovels, useChapters, useChapterContent, useCreateChapter, useSaveChapter, useDeleteChapter } from '../hooks/useNovels';
import { chaptersApi } from '../api/services';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import ProjectSwitcher from '../components/writer/ProjectSwitcher';
import ChapterList from '../components/writer/ChapterList';
import EditorArea from '../components/writer/EditorArea';
import NeuralTrace from '../components/writer/NeuralTrace';
import { logger } from '../utils/logger';
import { cn } from '../lib/utils';
import { Sparkles, FileText, Loader2, List, Plus, Trash2, Save, Edit } from 'lucide-react';

export default function Writer() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [selectedNovelId, setSelectedNovelId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('writer_selectedNovelId');
      return saved || null;
    }
    return null;
  });
  const [selectedChapterIndex, setSelectedChapterIndex] = useState<number | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('writer_selectedChapterIndex');
      return saved ? parseInt(saved, 10) : null;
    }
    return null;
  });
  const [showSidebar, setShowSidebar] = useState(true);
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1920);
  const [editorContent, setEditorContent] = useState<string>('');
  const [outlineContent, setOutlineContent] = useState<string>('');
  const [editMode, setEditMode] = useState<'body' | 'outline'>('body');

  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const minSize = 0.1 * windowWidth;
  const maxSize = 0.25 * windowWidth;
  const defaultSize = 0.15 * windowWidth;

  const { data: novels, isLoading: novelsLoading } = useNovels();
  const { data: chapters, isLoading: chaptersLoading } = useChapters(selectedNovelId);
  const { data: chapterContent } = useChapterContent(selectedNovelId, selectedChapterIndex);
  const { data: workflowState } = useWorkflowState(workflowId, !!workflowId);
  const { data: workflowTrace } = useWorkflowTrace(workflowId, !!workflowId);
  const startWorkflowMutation = useStartWorkflow();
  const createChapterMutation = useCreateChapter();
  const saveChapterMutation = useSaveChapter();
  const deleteChapterMutation = useDeleteChapter();

  const chapterContentQueries = useQueries({
    queries: (chapters || []).map((chapter) => ({
      queryKey: ['novels', selectedNovelId, 'chapters', chapter.index, 'wordcount'],
      queryFn: () => chaptersApi.get(selectedNovelId!, chapter.index),
      enabled: !!selectedNovelId && !!chapters && chapters.length > 0,
      staleTime: 60000,
      gcTime: 300000,
    })),
  });

  const wordCounts = useMemo(() => {
    const counts: Record<number, number> = {};
    if (chapters && chapters.length > 0 && chapterContentQueries.length === chapters.length) {
      chapters.forEach((chapter, index) => {
        const query = chapterContentQueries[index];
        if (query?.data?.content) {
          counts[chapter.index] = query.data.content.length;
        }
      });
    }
    return counts;
  }, [chapterContentQueries, chapters]);

  const currentNovel = novels?.find((n) => n.id === selectedNovelId);
  const selectedChapter = chapters?.find((c) => c.index === selectedChapterIndex);

  useEffect(() => {
    if (selectedNovelId) {
      logger.info('Writer', 'Novel selected', { novelId: selectedNovelId, novelTitle: currentNovel?.title });
      localStorage.setItem('writer_selectedNovelId', selectedNovelId);
    }
  }, [selectedNovelId, currentNovel]);

  useEffect(() => {
    if (selectedChapterIndex !== null) {
      logger.info('Writer', 'Chapter selected', { chapterIndex: selectedChapterIndex, chapterTitle: selectedChapter?.title });
      localStorage.setItem('writer_selectedChapterIndex', selectedChapterIndex.toString());
    }
  }, [selectedChapterIndex, selectedChapter]);

  useEffect(() => {
    if (workflowId) {
      logger.info('Writer', 'Workflow started', { workflowId });
    }
  }, [workflowId]);

  useEffect(() => {
    if (workflowState?.draft_content) {
      setEditorContent(workflowState.draft_content);
    } else if (chapterContent !== undefined) {
      setEditorContent(chapterContent?.content || '');
    }
  }, [workflowState?.draft_content, chapterContent, selectedChapterIndex]);

  useEffect(() => {
    if (chapterContent !== undefined) {
      setOutlineContent(chapterContent?.summary || '');
    }
  }, [chapterContent?.summary, selectedChapterIndex]);

  const handleStartWorkflow = async () => {
    logger.action('Writer', 'User clicked Start Workflow button', {
      novelId: selectedNovelId,
      chapterIndex: selectedChapterIndex,
      novelTitle: currentNovel?.title,
    });

    if (!selectedNovelId || selectedChapterIndex === null) {
      logger.warn('Writer', 'Cannot start workflow: no chapter selected');
      alert(t('common.select_chapter_first'));
      return;
    }

    if (!currentNovel) {
      logger.warn('Writer', 'Cannot start workflow: no novel selected');
      alert(t('common.select_novel_first'));
      return;
    }

    try {
      const result = await startWorkflowMutation.mutateAsync({
        novel_name: currentNovel.title,
        chapter_num: selectedChapterIndex,
      });
      setWorkflowId(result.workflow_id);
      logger.action('Writer', 'Workflow started successfully', {
        workflowId: result.workflow_id,
        novelName: currentNovel.title,
        chapterNum: selectedChapterIndex,
      });
      alert(t('common.task_started'));
    } catch (error) {
      logger.error('Writer', 'Failed to start workflow', { error });
      console.error(t('common.start_workflow_failed'), error);
    }
  };

  const handleGenerateOutline = async () => {
    if (!selectedNovelId || selectedChapterIndex === null) {
      alert(t('common.select_chapter_first'));
      return;
    }

    if (!currentNovel) {
      alert(t('common.select_novel_first'));
      return;
    }

    try {
      logger.action('Writer', 'Generate outline button clicked', {
        novelId: selectedNovelId,
        chapterIndex: selectedChapterIndex,
        novelName: currentNovel.title,
      });
      
      const result = await startWorkflowMutation.mutateAsync({
        novel_name: currentNovel.title,
        chapter_num: selectedChapterIndex,
      });
      
      setWorkflowId(result.workflow_id);
      logger.action('Writer', 'Generate outline started', {
        workflowId: result.workflow_id,
        taskId: result.task_id,
        architectPendingAfterSend: result.architect_pending_after_send,
        novelName: currentNovel.title,
        chapterNum: selectedChapterIndex,
      });
      const queueHint =
        typeof result.architect_pending_after_send === 'number'
          ? `；Architect 待消费队列（发送后）: ${result.architect_pending_after_send}`
          : '';
      alert(`任务已启动！工作流 ID: ${result.workflow_id}${queueHint}`);
    } catch (error: any) {
      logger.error('Writer', 'Failed to generate outline', { 
        error: error?.message || String(error),
        stack: error?.stack,
        response: error?.response?.data,
      });
      const errorMessage = error?.response?.data?.detail || error?.message || '生成大纲失败';
      alert(`生成大纲失败: ${errorMessage}`);
    }
  };

  const handleCreateChapter = async () => {
    if (!selectedNovelId) {
      alert(t('common.select_novel_first'));
      return;
    }

    const nextIndex = chapters && chapters.length > 0
      ? Math.max(...chapters.map(c => c.index)) + 1
      : 1;

    try {
      const newChapter = await createChapterMutation.mutateAsync({
        novel_id: selectedNovelId,
        index: nextIndex,
        title: undefined,
      });
      
      await queryClient.invalidateQueries({ queryKey: ['novels', selectedNovelId, 'chapters'] });
      await queryClient.refetchQueries({ queryKey: ['novels', selectedNovelId, 'chapters'] });
      
      if (newChapter && typeof newChapter.index === 'number') {
        setSelectedChapterIndex(newChapter.index);
      } else {
        setSelectedChapterIndex(nextIndex);
      }

      setEditorContent('');
      logger.action('Writer', 'Chapter created', { novelId: selectedNovelId, index: newChapter?.index || nextIndex, chapterId: newChapter?.id });
    } catch (error) {
      logger.error('Writer', 'Failed to create chapter', { error });
      alert('创建章节失败');
    }
  };

  const handleSaveChapter = async () => {
    if (!selectedNovelId || selectedChapterIndex === null) {
      alert(t('common.select_chapter_first'));
      return;
    }

    try {
      await saveChapterMutation.mutateAsync({
        novelId: selectedNovelId,
        chapterIndex: selectedChapterIndex,
        data: {
          content: editorContent,
          summary: outlineContent,
        },
      });
      logger.action('Writer', 'Chapter saved', { novelId: selectedNovelId, chapterIndex: selectedChapterIndex });
      alert('保存成功');
    } catch (error) {
      logger.error('Writer', 'Failed to save chapter', { error });
      alert('保存失败');
    }
  };

  const handleEditChapterTitle = async () => {
    if (!selectedNovelId || selectedChapterIndex === null) {
      alert(t('common.select_chapter_first'));
      return;
    }

    const currentTitle = selectedChapter?.title || '';
    const newTitle = prompt('请输入章节名：', currentTitle);
    
    if (newTitle === null) {
      return;
    }

    if (newTitle === currentTitle) {
      return;
    }

    try {
      await saveChapterMutation.mutateAsync({
        novelId: selectedNovelId,
        chapterIndex: selectedChapterIndex,
        data: {
          title: newTitle.trim() || undefined,
        },
      });
      logger.action('Writer', 'Chapter title updated', { 
        novelId: selectedNovelId, 
        chapterIndex: selectedChapterIndex,
        oldTitle: currentTitle,
        newTitle: newTitle.trim() || undefined,
      });
    } catch (error) {
      logger.error('Writer', 'Failed to update chapter title', { error });
      alert('修改章节名失败');
    }
  };

  const handleDeleteChapter = async () => {
    if (!selectedNovelId || selectedChapterIndex === null) {
      alert(t('common.select_chapter_first'));
      return;
    }

    const chapterTitle = selectedChapter?.title || '';
    const chapterDisplay = chapterTitle 
      ? `第 ${selectedChapterIndex} 章 ${chapterTitle}`
      : `第 ${selectedChapterIndex} 章`;
    const novelTitle = currentNovel?.title || t('common.no_novel_selected');
    const wordCount = wordCounts[selectedChapterIndex] || 0;
    
    const confirmMessage = `确定要删除此章节吗？\n\n小说：${novelTitle}\n章节：${chapterDisplay}\n字数：${wordCount}${t('writer.editor.words')}`;

    if (!confirm(confirmMessage)) {
      return;
    }

    try {
      await deleteChapterMutation.mutateAsync({
        novelId: selectedNovelId,
        chapterIndex: selectedChapterIndex,
      });
      setSelectedChapterIndex(null);
      setEditorContent('');
      logger.action('Writer', 'Chapter deleted', { novelId: selectedNovelId, chapterIndex: selectedChapterIndex });
    } catch (error) {
      logger.error('Writer', 'Failed to delete chapter', { error });
      alert('删除失败');
    }
  };

  return (
    <div className="h-full w-full flex flex-col bg-zinc-950 overflow-hidden -mt-8">
      <div className="h-14 flex items-center justify-between px-6 bg-black/50 border-b border-white/10 backdrop-blur-xl relative z-40">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowSidebar(!showSidebar)}
            className="lg:hidden"
          >
            <List className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <span>{currentNovel?.title || t('common.no_novel_selected')}</span>
            {selectedChapter && (
              <>
                <span>/</span>
                <span>{selectedChapter.title || t('common.chapter_format', { index: selectedChapter.index })}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCreateChapter}
            disabled={!selectedNovelId || createChapterMutation.isPending}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            {createChapterMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Plus className="w-4 h-4 mr-2" />
            )}
            新增章节
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDeleteChapter}
            disabled={!selectedChapterIndex || deleteChapterMutation.isPending}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            {deleteChapterMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4 mr-2" />
            )}
            删除章节
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleEditChapterTitle}
            disabled={!selectedChapterIndex || saveChapterMutation.isPending}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <Edit className="w-4 h-4 mr-2" />
            修改章节名
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSaveChapter}
            disabled={!selectedChapterIndex || saveChapterMutation.isPending}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            {saveChapterMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            保存章节
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleGenerateOutline}
            disabled={!selectedChapterIndex || startWorkflowMutation.isPending}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            {startWorkflowMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <FileText className="w-4 h-4 mr-2" />
            )}
            {t('writer.toolbar.generate_outline')}
          </Button>
          <Button
            size="sm"
            onClick={handleStartWorkflow}
            disabled={!selectedChapterIndex || startWorkflowMutation.isPending}
            className="shadow-lg shadow-indigo-500/50 hover:shadow-indigo-500/70"
          >
            {startWorkflowMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4 mr-2" />
            )}
            {t('writer.toolbar.start_workflow')}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative z-0">
        <PanelGroup orientation="horizontal" className="h-full w-full">
          {showSidebar && (
            <>
              <Panel defaultSize={defaultSize} minSize={minSize} maxSize={maxSize}>
                <div className="h-full w-full flex flex-col bg-zinc-900/30 overflow-hidden relative z-0">
                  <div className="p-4 border-b border-white/5 flex-shrink-0">
                    <ProjectSwitcher
                      novels={novels || []}
                      currentNovelId={selectedNovelId}
                      onNovelChange={setSelectedNovelId}
                      isLoading={novelsLoading}
                    />
                  </div>
                  <ScrollArea className="flex-1 min-w-0">
                    {chaptersLoading ? (
                      <div className="p-8 flex items-center justify-center">
                        <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
                      </div>
                    ) : (
                      <ChapterList
                        chapters={chapters || []}
                        selectedIndex={selectedChapterIndex}
                        onSelect={setSelectedChapterIndex}
                        wordCounts={wordCounts}
                      />
                    )}
                  </ScrollArea>
                </div>
              </Panel>
              <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-indigo-500/50 transition-colors group">
                <div className="w-full h-full flex items-center justify-center">
                  <div className="w-0.5 h-8 bg-indigo-500/0 group-hover:bg-indigo-500/50 transition-colors rounded"></div>
                </div>
              </PanelResizeHandle>
            </>
          )}

          <Panel defaultSize={showSidebar ? 35 : 100} minSize={25}>
            <div className="h-full flex flex-col">
              {selectedChapterIndex !== null && (
                <div className="flex-shrink-0 flex items-center gap-1 border-b border-zinc-800 bg-zinc-950/50 px-3 py-1.5">
                  <button
                    type="button"
                    onClick={() => setEditMode('body')}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                      editMode === 'body'
                        ? 'bg-indigo-600/80 text-white'
                        : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                    )}
                  >
                    正文
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditMode('outline')}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                      editMode === 'outline'
                        ? 'bg-indigo-600/80 text-white'
                        : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                    )}
                  >
                    大纲
                  </button>
                </div>
              )}
              <div className="flex-1 min-h-0">
                <EditorArea
                  chapterId={selectedChapterIndex}
                  content={
                    editMode === 'body'
                      ? workflowState?.draft_content || chapterContent?.content || editorContent || ''
                      : outlineContent
                  }
                  onContentChange={editMode === 'body' ? setEditorContent : setOutlineContent}
                  mode={editMode}
                />
              </div>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-indigo-500/50 transition-colors group">
            <div className="w-full h-full flex items-center justify-center">
              <div className="w-0.5 h-8 bg-indigo-500/0 group-hover:bg-indigo-500/50 transition-colors rounded"></div>
            </div>
          </PanelResizeHandle>

          <Panel defaultSize={showSidebar ? defaultSize : 0} minSize={minSize} maxSize={maxSize}>
            <div className="h-full w-full flex flex-col bg-zinc-950/50 overflow-hidden">
              <div className="h-16 flex items-center px-8 border-b border-white/5 flex-shrink-0">
                <h2 className="text-lg font-semibold text-zinc-100 leading-tight">{t('writer.trace.title')}</h2>
              </div>
              <ScrollArea className="flex-1 min-w-0">
                <NeuralTrace logs={workflowTrace?.logs || []} />
              </ScrollArea>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
