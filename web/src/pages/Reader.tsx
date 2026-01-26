import * as React from 'react';
import { useState, useMemo } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { useQueries } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNovels, useChapters, useChapterContent } from '../hooks/useNovels';
import { chaptersApi } from '../api/services';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import ProjectSwitcher from '../components/writer/ProjectSwitcher';
import ChapterList from '../components/writer/ChapterList';
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, List, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

/** 阅读助手：小说列表、目录、正文均来自 useNovels/useChapters/useChapterContent → novels API（数据库）。 */
export default function Reader() {
  const { t } = useTranslation();
  const [selectedNovelId, setSelectedNovelId] = useState<string | null>(null);
  const [selectedChapterIndex, setSelectedChapterIndex] = useState<number | null>(null);
  const [showNav, setShowNav] = React.useState(true);
  const [isNarrow, setIsNarrow] = React.useState(false);
  const [showSidebar, setShowSidebar] = React.useState(true);
  const [windowWidth, setWindowWidth] = React.useState(typeof window !== 'undefined' ? window.innerWidth : 1920);
  const lastScrollY = React.useRef(0);

  React.useEffect(() => {
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

  const chapterContentQueries = useQueries({
    queries: (chapters || []).map((chapter) => ({
      queryKey: ['novels', selectedNovelId, 'chapters', chapter.index, 'wordcount'],
      queryFn: () => chaptersApi.get(selectedNovelId!, chapter.index),
      enabled: !!selectedNovelId && !!chapters && chapters.length > 0,
      staleTime: 60000,
      gcTime: 300000,
    })),
  });

  const wordCounts = React.useMemo(() => {
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
  const currentIndex = chapters?.findIndex((c) => c.index === selectedChapterIndex) ?? -1;

  React.useEffect(() => {
    if (!selectedNovelId && novels && novels.length > 0) {
      setSelectedNovelId(novels[0].id);
    }
  }, [novels]);

  React.useEffect(() => {
    if (selectedNovelId && selectedChapterIndex === null && chapters && chapters.length > 0) {
      setSelectedChapterIndex(chapters[0].index);
    }
  }, [selectedNovelId, chapters]);

  React.useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY > lastScrollY.current && currentScrollY > 100) {
        setShowNav(false);
      } else {
        setShowNav(true);
      }
      lastScrollY.current = currentScrollY;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handlePrev = () => {
    if (chapters && currentIndex > 0) {
      setSelectedChapterIndex(chapters[currentIndex - 1].index);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleNext = () => {
    if (chapters && currentIndex < chapters.length - 1) {
      setSelectedChapterIndex(chapters[currentIndex + 1].index);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <div className="h-full w-full flex flex-col bg-zinc-900 text-zinc-100 overflow-hidden -mt-8">
      <div className="h-14 flex items-center justify-between px-6 bg-black/50 border-b border-white/10 backdrop-blur-xl relative z-40">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowSidebar(!showSidebar)}
            className="text-zinc-300 hover:bg-white/10"
          >
            <List className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <span>{currentNovel?.title || t('reader.no_novel_selected')}</span>
            {selectedChapter && (
              <>
                <span>/</span>
                <span>{selectedChapter.title || t('common.chapter_format', { index: selectedChapter.index })}</span>
              </>
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsNarrow(!isNarrow)}
          className="text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
        >
          {isNarrow ? (
            <Maximize2 className="w-4 h-4" />
          ) : (
            <Minimize2 className="w-4 h-4" />
          )}
        </Button>
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

          <Panel defaultSize={showSidebar ? 80 : 100}>
            <div className="h-full w-full overflow-auto bg-zinc-900 text-zinc-100">
              <div className={`mx-auto py-12 transition-all duration-300 ${isNarrow ? 'max-w-4xl px-8' : 'w-full px-16'}`}>
                {chapterContent?.content ? (
                  <>
                    <div className={`prose prose-invert prose-lg max-w-none font-serif leading-loose ${isNarrow ? '' : 'max-w-5xl mx-auto'}`}>
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p className="mb-6 leading-relaxed whitespace-pre-wrap break-words">{children}</p>,
                          img: ({ src, alt }) => (
                            <img src={src} alt={alt} className="my-8 rounded-lg max-w-full h-auto" />
                          ),
                        }}
                      >
                        {chapterContent.content.replace(/  +/g, '\n\n')}
                      </ReactMarkdown>
                    </div>

                    <div className={`mt-20 pt-12 border-t border-zinc-800 flex items-center justify-between ${isNarrow ? '' : 'max-w-5xl mx-auto'}`}>
                      <Button
                        variant="outline"
                        onClick={handlePrev}
                        disabled={currentIndex <= 0}
                        className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                      >
                        <ChevronLeft className="w-4 h-4 mr-2" />
                        {t('reader.prev_chapter')}
                      </Button>
                      <span className="text-zinc-500 text-sm font-mono">
                        {currentIndex + 1} / {chapters?.length || 0}
                      </span>
                      <Button
                        variant="outline"
                        onClick={handleNext}
                        disabled={currentIndex >= (chapters?.length || 0) - 1}
                        className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                      >
                        {t('reader.next_chapter')}
                        <ChevronRight className="w-4 h-4 ml-2" />
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="relative text-center py-32">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-600 rounded-full blur-3xl opacity-10 pointer-events-none"></div>
                    <p className="relative text-zinc-500 text-lg leading-relaxed">{t('reader.select_novel_chapter')}</p>
                  </div>
                )}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
