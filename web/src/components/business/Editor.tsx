import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface EditorProps {
  content: string;
  onChange?: (content: string) => void;
  readOnly?: boolean;
}

export default function Editor({ content, onChange, readOnly = false }: EditorProps) {
  const [localContent, setLocalContent] = useState(content);

  useEffect(() => {
    setLocalContent(content);
  }, [content]);

  const handleChange = (value: string) => {
    setLocalContent(value);
    onChange?.(value);
  };

  const estimateTokens = (text: string): number => {
    const chineseChars = (text.match(/[\u4e00-\u9fff]/g) || []).length;
    const otherChars = text.length - chineseChars;
    return Math.ceil(chineseChars / 1.5 + otherChars / 4);
  };

  const tokenCount = estimateTokens(localContent);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
        <span className="text-sm text-gray-600">Markdown 编辑器</span>
        <span className="text-xs text-gray-500">Token 估算: {tokenCount}</span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 border-r border-gray-200">
          <textarea
            value={localContent}
            onChange={(e) => handleChange(e.target.value)}
            readOnly={readOnly}
            className={`w-full h-full p-4 font-mono text-sm resize-none focus:outline-none ${
              readOnly ? 'bg-gray-50 cursor-not-allowed' : 'bg-white'
            }`}
            placeholder="开始输入 Markdown 内容..."
          />
        </div>

        <div className="flex-1 overflow-y-auto p-4 bg-gray-50 prose prose-sm max-w-none">
          <ReactMarkdown>{localContent || '*暂无内容*'}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
