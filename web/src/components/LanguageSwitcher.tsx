import * as React from 'react';
import { Languages, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

const languages = [
  { code: 'zh-CN', label: '简体中文', nativeLabel: '简体中文' },
  { code: 'zh-TW', label: '繁体中文', nativeLabel: '繁體中文' },
  { code: 'en', label: 'English', nativeLabel: 'English' },
  { code: 'ja', label: '日本語', nativeLabel: '日本語' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const [isOpen, setIsOpen] = React.useState(false);
  const currentLang = languages.find((lang) => lang.code === i18n.language) || languages[0];

  const handleLanguageChange = (langCode: string) => {
    i18n.changeLanguage(langCode);
    setIsOpen(false);
  };

  return (
    <div className="relative z-[10000]">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        className="relative z-[10000]"
      >
        <Languages className="w-4 h-4" />
      </Button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-[9999]"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 top-full mt-2 w-48 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-md shadow-lg z-[10000]">
            {languages.map((lang) => (
              <button
                key={lang.code}
                onClick={() => handleLanguageChange(lang.code)}
                className={cn(
                  'w-full px-4 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700 flex items-center justify-between transition-colors',
                  i18n.language === lang.code && 'bg-zinc-100 dark:bg-zinc-700'
                )}
              >
                <span>{lang.nativeLabel}</span>
                {i18n.language === lang.code && (
                  <Check className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
