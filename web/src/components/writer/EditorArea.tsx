import { useState, useEffect } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { useTranslation } from 'react-i18next';
import { ScrollArea } from '../ui/scroll-area';
import { logger } from '../../utils/logger';
import { FileText, Eye } from 'lucide-react';
import { cn } from '../../lib/utils';
import ReactMarkdown from 'react-markdown';

type EditorMode = 'body' | 'outline';

interface EditorAreaProps {
  chapterId: number | null;
  content: string;
  onContentChange?: (content: string) => void;
  /** 正文 | 大纲，用于切换显示标签与占位符 */
  mode?: EditorMode;
}

export default function EditorArea({ chapterId, content, onContentChange, mode = 'body' }: EditorAreaProps) {
  const { t } = useTranslation();
  const [markdown, setMarkdown] = useState(content || '');
  const isOutline = mode === 'outline';

  useEffect(() => {
    setMarkdown(content || '');
    logger.info('EditorArea', 'Content updated', {
      chapterId,
      contentLength: (content || '').length,
      mode,
    });
  }, [content, chapterId, mode]);

  const wordCount = markdown.split(/\s+/).filter(Boolean).length;
  const estimatedTokens = Math.ceil(wordCount * 1.3);

  if (!chapterId) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <FileText className="w-16 h-16 mx-auto text-zinc-700 mb-4" />
          <h3 className="text-lg font-semibold text-zinc-300 mb-2">
            {t('writer.editor.select_chapter')}
          </h3>
          <p className="text-sm text-zinc-500">
            {t('writer.editor.select_chapter_desc')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <PanelGroup orientation="horizontal" className="h-full w-full">
      <Panel defaultSize={50} minSize={30}>
        <div className="h-full flex flex-col bg-zinc-900 border-r border-zinc-800">
          <div className="h-10 flex items-center justify-between px-4 border-b border-zinc-800 bg-zinc-950/50">
            <span className="text-xs font-medium text-zinc-400">
              {isOutline ? '大纲' : t('writer.editor.markdown_editor')}
            </span>
            <div className="flex items-center gap-4 text-xs text-zinc-500 font-mono">
              <span>{wordCount} {t('writer.editor.words')}</span>
              <span>~{estimatedTokens} tokens</span>
            </div>
          </div>
          <ScrollArea className="flex-1">
            <textarea
              value={markdown}
              onChange={(e) => {
                setMarkdown(e.target.value);
                onContentChange?.(e.target.value);
              }}
              className="w-full h-full p-6 font-mono text-sm text-zinc-100 bg-transparent resize-none focus:outline-none placeholder:text-zinc-600"
              placeholder={isOutline ? '填写本章大纲…' : t('writer.editor.placeholder')}
              style={{ fontFamily: 'JetBrains Mono, monospace' }}
            />
          </ScrollArea>
        </div>
      </Panel>

      <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-indigo-500/50 transition-colors group">
        <div className="w-full h-full flex items-center justify-center">
          <div className="w-0.5 h-8 bg-indigo-500/0 group-hover:bg-indigo-500/50 transition-colors rounded"></div>
        </div>
      </PanelResizeHandle>

      <Panel defaultSize={50} minSize={30}>
        <div className="h-full flex flex-col bg-zinc-950">
          <div className="h-10 flex items-center px-4 border-b border-zinc-800 bg-zinc-950/50">
            <Eye className="w-4 h-4 mr-2 text-zinc-400" />
            <span className="text-xs font-medium text-zinc-400">
              {isOutline ? '大纲预览' : t('writer.editor.preview')}
            </span>
          </div>
          <ScrollArea className="flex-1 p-8">
            <div className="prose prose-invert prose-lg max-w-none">
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="mb-6 leading-relaxed whitespace-pre-wrap break-words">{children}</p>,
                  img: ({ src, alt }) => (
                    <img src={src} alt={alt} className="my-8 rounded-lg max-w-full h-auto" />
                  ),
                }}
              >
                {(markdown || t('writer.editor.no_content')).replace(/  +/g, '\n\n')}
              </ReactMarkdown>
            </div>
          </ScrollArea>
        </div>
      </Panel>
    </PanelGroup>
  );
}
