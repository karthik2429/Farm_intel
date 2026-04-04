import React from 'react';

import { useNavigate, useLocation } from 'react-router-dom';
import { Home, TrendingUp, Bot, Sprout, ShoppingCart } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

const BottomNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useLanguage();

  const tabs = [
    { path: '/home', icon: Home, label: t('home') },
    { path: '/market', icon: TrendingUp, label: t('marketNav') },
    { path: '/ai-chat', icon: Bot, label: t('aiApp') },
    { path: '/crops', icon: Sprout, label: t('crops') },
    { path: '/marketplace', icon: ShoppingCart, label: t('marketplace') },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 glass-card border-t border-border/50 rounded-none">
      <div className="flex items-center justify-around py-2 px-2 max-w-lg mx-auto">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path;
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-xl transition-all ${
                isActive
                  ? 'text-primary bg-primary/10'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <tab.icon className="w-5 h-5" />
              <span className="text-[10px] font-semibold">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};

export default BottomNav;
