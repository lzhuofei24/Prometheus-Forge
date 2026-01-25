import { useTranslation } from 'react-i18next';
import { logger } from '../../utils/logger';
import { cn } from '../../lib/utils';
import type { Chapter } from '../../types';

interface ChapterListProps {
  chapters: Chapter[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  wordCounts?: Record<number, number>;
}

export default function ChapterList({ chapters, selectedIndex, onSelect, wordCounts = {} }: ChapterListProps) {
  const { t } = useTranslation();
  if (chapters.length === 0) {
    return (
      <div className="p-8 text-center text-zinc-500 text-sm leading-relaxed">
        {t('writer.sidebar.no_chapters')}
      </div>
    );
  }

  return (
    <div className="p-4">
      {chapters.map((chapter) => (
        <div
          key={chapter.id}
          onClick={() => {
            logger.action('ChapterList', 'User selected chapter', {
              chapterId: chapter.id,
              chapterIndex: chapter.index,
              chapterTitle: chapter.title,
            });
            onSelect(chapter.index);
          }}
          className={cn(
            'p-4 rounded-lg mb-3 cursor-pointer transition-colors',
            selectedIndex === chapter.index
              ? 'bg-indigo-500/10'
              : 'hover:bg-white/5'
          )}
        >
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-zinc-200 leading-relaxed">
              第 {chapter.index} 章{chapter.title ? ` ${chapter.title}` : ''}
            </span>
            <span className="text-xs text-zinc-500 leading-relaxed">
              （{wordCounts[chapter.index] || 0}{t('writer.editor.words')}）
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
