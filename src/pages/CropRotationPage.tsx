import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Leaf, TrendingUp, Bug } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';

const CropRotationPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const rotationPlan = [
    {
      season: t('kharif') + ' 2024',
      crop: 'Mustard',
      family: 'Brassicaceae',
      duration: '90 Days',
      img: cropCotton,
      reasons: [
        { icon: Leaf, label: t('fixesNitrogen') },
        { icon: TrendingUp, label: t('marketDemand') },
        { icon: Bug, label: t('pestBreak') },
      ],
    },
    {
      season: t('rabi') + ' 2024',
      crop: 'Chickpea (Gram)',
      family: 'Legume Family',
      duration: '110 Days',
      img: cropRice,
      reasons: [
        { icon: Leaf, label: t('fixesNitrogen') },
        { icon: TrendingUp, label: t('marketDemand') },
        { icon: Bug, label: t('pestBreak') },
      ],
    },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">{t('rotationPlanner')}</h1>
      </div>

      <div className="px-5 space-y-4">
        {rotationPlan.map((plan, i) => (
          <div key={i} className="glass-card overflow-hidden">
            <div className="relative h-32">
              <img src={plan.img} alt={plan.crop} className="w-full h-full object-cover" loading="lazy" width={512} height={512} />
              <div className="absolute inset-0 bg-gradient-to-t from-card to-transparent" />
              <div className="absolute bottom-3 left-3">
                <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-[10px] font-bold">
                  {plan.season}
                </span>
              </div>
            </div>
            <div className="p-4">
              <h3 className="text-base font-extrabold text-foreground">{plan.crop}</h3>
              <p className="text-xs text-muted-foreground">{plan.family} • {plan.duration}</p>

              <div className="mt-3">
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">{t('whyThisCrop')}</p>
                <div className="flex gap-2">
                  {plan.reasons.map((r, j) => (
                    <div key={j} className="flex items-center gap-1 bg-primary/10 px-2 py-1 rounded-full">
                      <r.icon className="w-3 h-3 text-primary" />
                      <span className="text-[10px] text-primary font-semibold">{r.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <BottomNav />
    </div>
  );
};

export default CropRotationPage;
