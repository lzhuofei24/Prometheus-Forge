import * as React from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Settings, Github, Moon, Sun } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '../ui/tabs.tsx';
import { Button } from '../ui/button';
import LanguageSwitcher from '../LanguageSwitcher';

export default function MainLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [theme, setTheme] = React.useState<'light' | 'dark'>('light');

  const navItems = [
    { path: '/', label: t('nav.home'), value: 'home' },
    { path: '/writer', label: t('nav.writer'), value: 'writer' },
    { path: '/reader', label: t('nav.reader'), value: 'reader' },
    { path: '/workflow', label: t('nav.workflow'), value: 'workflow' },
    { path: '/resources', label: t('nav.resources'), value: 'resources' },
    { path: '/prompts', label: t('nav.prompts'), value: 'prompts' },
    { path: '/approvals', label: t('nav.approvals', '审批助手'), value: 'approvals' },
  ];

  const currentValue = navItems.find((item) => location.pathname === item.path)?.value || 'home';

  const handleTabChange = (value: string) => {
    const item = navItems.find((i) => i.value === value);
    if (item) {
      navigate(item.path);
    }
  };

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.classList.toggle('dark', newTheme === 'dark');
  };

  return (
    <div className="h-screen flex flex-col bg-zinc-50 dark:bg-zinc-900">
      <nav className="h-12 bg-black/50 dark:bg-black/50 backdrop-blur-xl border-b border-white/10 relative z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between">
          <div className="flex items-center gap-6 flex-nowrap">
            <div className="flex items-center gap-2 flex-shrink-0">
              <BookOpen className="w-5 h-5 text-indigo-400" />
              <span className="text-lg font-bold text-zinc-100 tracking-tight whitespace-nowrap">Prometheus Forge</span>
            </div>

            <Tabs value={currentValue} onValueChange={handleTabChange}>
              <TabsList className="bg-transparent p-0 h-auto gap-0">
                {navItems.map((item, index) => (
                  <React.Fragment key={item.value}>
                    <TabsTrigger
                      value={item.value}
                      className="px-3 py-1.5 h-8 text-sm rounded-md border border-transparent data-[state=active]:border-indigo-500/50 data-[state=active]:bg-indigo-500/10 data-[state=active]:text-indigo-400 data-[state=active]:shadow-none hover:bg-white/5 text-zinc-300 transition-all whitespace-nowrap"
                    >
                      {item.label}
                    </TabsTrigger>
                    {index < navItems.length - 1 && (
                      <div className="w-px h-4 bg-white/10 mx-12"></div>
                    )}
                  </React.Fragment>
                ))}
              </TabsList>
            </Tabs>
          </div>

          <div className="flex items-center gap-1 flex-shrink-0">
            <LanguageSwitcher />
            <Button variant="ghost" size="sm" onClick={toggleTheme} className="text-zinc-300 hover:bg-white/10 h-8 w-8 p-0">
              {theme === 'light' ? (
                <Moon className="w-4 h-4" />
              ) : (
                <Sun className="w-4 h-4" />
              )}
            </Button>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center rounded-md h-8 w-8 p-0 text-zinc-300 hover:bg-white/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              <Github className="w-4 h-4" />
            </a>
            <Button variant="ghost" size="sm" className="text-zinc-300 hover:bg-white/10 h-8 w-8 p-0">
              <Settings className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </nav>

      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
